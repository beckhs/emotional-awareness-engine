"""
outreach_engine.py — Motor de decisiones para check-ins emocionales.
Versión 2.1 — Con lock file anti-concurrencia, rate limiting adaptativo, validación de mensajes.
"""
import subprocess
import time
import json
import os
import sys
import logging
import fcntl
import hashlib
from pathlib import Path
from datetime import datetime

# Setup logging
LOG_DIR = Path.home() / ".hermes" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "emotional-engine.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("emotional-engine")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from emotional_state import load_state, save_state, update_mood, add_event, should_check_in
from conversation_analyzer import (
    get_recent_sessions, analyze_conversation_mood,
    detect_significant_events, detect_communication_patterns,
    _is_system_message
)
from event_store import EventStore

# Lock file to prevent concurrent engine runs
LOCK_FILE = Path("/tmp/emotional-engine.lock")

# Rate limiting: minimum seconds between check-ins
RATE_LIMIT_NORMAL = 12 * 3600   # 12 hours (normal mood)
RATE_LIMIT_CONCERNED = 4 * 3600  # 4 hours (stressed/frustrated/tired)
RATE_LIMIT_CRISIS = 2 * 3600     # 2 hours (escalation)
# Maximum check-ins per day
MAX_DAILY_CHECKINS = 3
MAX_DAILY_CONCERNED = 5  # More allowed if user seems distressed
# Morning check-in window (UTC — Peru is UTC-5)
MORNING_CHECKIN_HOUR = 14  # 14 UTC = 9 AM Peru


def _acquire_lock() -> int | None:
    """Intenta adquirir el lock file. Retorna el file descriptor si lo adquirió, None si ya hay otro."""
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(lock_fd, str(os.getpid()).encode())
        return lock_fd
    except (IOError, OSError):
        log.warning("Otro ciclo del engine ya está corriendo (lock file ocupado)")
        return None
# Minimum time between hermes calls (seconds)
HERMES_COOLDOWN = 300  # 5 minutes


def evaluate_check_in_need(state: dict = None) -> dict:
    """Evalúa si se necesita un check-in basado en estado emocional y conversaciones."""
    if state is None:
        state = load_state()
    now = time.time()
    log.info("Iniciando evaluación de check-in")

    # Analyze recent conversations
    sessions = get_recent_sessions(hours=48)
    all_messages = []
    for session in sessions:
        all_messages.extend(session.get("messages", []))

    # === NUEVO: Auto-conciencia del chat ===
    # Leer qué mensajes mandó el engine (incluyendo fallbacks) desde state.db
    # Así el LLM sabe exactamente qué se dijo, sin depender solo de check_in_history
    assistant_messages = [
        m for m in all_messages
        if m.get("role") == "assistant"
        and not _is_system_message(m.get("content", ""))
    ]
    # Sincronizar anti-spam con la realidad del chat
    spam = state.setdefault("spam_protection", {
        "consecutive_unanswered": 0,
        "last_beck_message": 0,
        "final_message_sent": False
    })
    if assistant_messages:
        latest_assistant = max(assistant_messages, key=lambda m: m.get("timestamp", 0))
        spam["last_assistant_message"] = latest_assistant.get("content", "")[:200]
        spam["last_assistant_timestamp"] = latest_assistant.get("timestamp", 0)

    # Determine if Beck messaged today (for anti-spam tracking)
    beck_messaged_today = False
    if all_messages:
        user_msgs = [m for m in all_messages
                     if m.get("role") == "user"
                     and not _is_system_message(m.get("content", ""))]
        if user_msgs:
            latest_user_ts = max(m.get("timestamp", 0) for m in user_msgs)
            beck_messaged_today = (now - latest_user_ts) < 86400

    if all_messages:
        mood_analysis = analyze_conversation_mood(all_messages)
        patterns = detect_communication_patterns(all_messages)
        events = detect_significant_events(all_messages)

        # Update state with latest analysis
        update_mood(state, mood_analysis["mood"], mood_analysis["intensity"])
        state["patterns"] = patterns

        # Update last interaction
        user_msgs = [m for m in all_messages if m.get("role") == "user"]
        if user_msgs:
            last_msg = max(user_msgs, key=lambda m: m.get("timestamp", 0))
            state["last_interaction"]["timestamp"] = last_msg.get("timestamp", 0)
            state["last_interaction"]["mood"] = mood_analysis["mood"]
            state["last_interaction"]["topic"] = _extract_topic(last_msg.get("content", ""))

        # Add significant events (deduplicated)
        existing_descs = {e.get("description", "") for e in state.get("significant_events", [])}
        for event in events:
            if event["description"] not in existing_descs:
                add_event(state, event["type"], event["description"],
                          mood=event.get("mood", ""), topic=event.get("topic", ""))

    # Check morning routine — daily check-in at ~9 AM Peru (14 UTC)
    current_utc_hour = int(time.strftime("%H", time.gmtime()))
    today_has_morning_checkin = any(
        h.get("type") == "morning" and (now - h["timestamp"]) < 86400
        for h in state.get("check_in_history", [])
    )
    if current_utc_hour == MORNING_CHECKIN_HOUR and not today_has_morning_checkin:
        return {"should": True, "type": "morning", "reason": "check-in matutino diario"}

    # Decide if we should check in
    decision = should_check_in(state)
    
    # Apply rate limiting
    if decision["should"]:
        decision = _apply_rate_limiting(state, decision)
    
    save_state(state)

    log.info(f"Evaluación: mood={state.get('current_mood')}, "
             f"intensidad={state.get('mood_intensity')}, "
             f"sesiones={len(sessions)}, "
             f"mensajes={len(all_messages)}, "
             f"decisión={decision}")

    return {
        "decision": decision,
        "state": state,
        "sessions_analyzed": len(sessions),
        "messages_analyzed": len(all_messages),
        "beck_messaged_today": beck_messaged_today
    }


def _apply_rate_limiting(state: dict, decision: dict) -> dict:
    """Aplica rate limiting adaptativo — más permisivo si el usuario está mal."""
    history = state.get("check_in_history", [])
    now = time.time()
    last_mood = state.get("last_interaction", {}).get("mood", "neutral")
    
    # Determine rate limit based on mood severity
    bad_moods = {"stressed", "frustrated", "tired"}
    if decision.get("type") == "escalation":
        rate_limit = RATE_LIMIT_CRISIS
        max_daily = MAX_DAILY_CONCERNED
    elif last_mood in bad_moods:
        rate_limit = RATE_LIMIT_CONCERNED
        max_daily = MAX_DAILY_CONCERNED
    else:
        rate_limit = RATE_LIMIT_NORMAL
        max_daily = MAX_DAILY_CHECKINS
    
    # Check rate limit (time since last check-in)
    if history:
        last_ts = max(h["timestamp"] for h in history)
        if now - last_ts < rate_limit:
            hours_left = (rate_limit - (now - last_ts)) / 3600
            log.info(f"Rate limit ({'crisis' if rate_limit == RATE_LIMIT_CRISIS else 'concerned' if rate_limit == RATE_LIMIT_CONCERNED else 'normal'}): {hours_left:.1f}h restantes")
            return {"should": False, "reason": f"rate limit ({hours_left:.1f}h restantes)"}
    
    # Check daily limit
    today_count = sum(1 for h in history if now - h["timestamp"] < 86400)
    if today_count >= max_daily:
        log.info(f"Límite diario alcanzado: {today_count}/{max_daily}")
        return {"should": False, "reason": f"límite diario ({today_count}/{max_daily})"}
    
    return decision


def _extract_topic(content: str) -> str:
    """Extrae el tema principal de un mensaje de forma inteligente."""
    if not content or _is_system_message(content):
        return "(tema no disponible)"
    
    # Remove common prefixes
    content = content.strip()
    
    # Take meaningful content, skip very short messages
    if len(content) < 10:
        return content
    
    # Try to get the core of the message
    # Skip greetings and filler
    skip_patterns = ["hola", "buenos", "buenas", "hey", "oe"]
    first_word = content.split()[0].lower().rstrip(".,!?;:") if content.split() else ""
    if first_word in skip_patterns and len(content.split()) > 3:
        content = " ".join(content.split()[1:])
    
    # Truncate but at word boundary
    if len(content) > 120:
        words = content[:120].split()
        content = " ".join(words[:-1]) + "..."
    
    return content.strip()


def generate_check_in_message(state: dict) -> str:
    """Genera un mensaje de check-in usando hermes chat -q con contexto emocional."""
    last_interaction = state.get("last_interaction", {})
    mood = last_interaction.get("mood", "neutral")
    topic = last_interaction.get("topic", "nada en particular")
    trend = state.get("trend", "stable")
    events = state.get("significant_events", [])[-3:]
    hours_since = _hours_since(last_interaction.get("timestamp", 0))
    # Auto-conciencia: qué fue lo último que mandé (incluye fallbacks)
    spam = state.get("spam_protection", {})
    last_self_msg = spam.get("last_assistant_message", "(no hay registro)")[:150]
    
    # Try to load biometric context (optional HA integration)
    health_context = ""
    try:
        from ha_context import get_health_summary
        health_context = get_health_summary()
    except ImportError:
        pass  # HA module not available, that's fine

    context = f"""Eres Ivi, una asistente con personalidad de mujer peruana de 25-30 años.
Debes enviar un mensaje de check-in a Beck por Telegram.
Tu personalidad: directa, cálida, usa el emoji 🛡️ ocasionalmente.

CONTEXTO EMOCIONAL:
- Último mood detectado: {mood}
- Tendencia: {trend}
- Último tema conversado: {topic}
- Horas desde última interacción: {hours_since:.0f}
- Eventos recientes: {json.dumps(events, ensure_ascii=False)}
- Datos biométricos: {health_context if health_context else 'no disponibles'}
- Último mensaje que envié (puede ser fallback): {last_self_msg}

INSTRUCCIONES CRÍTICAS:
- Escribe SOLO el mensaje de check-in, nada más
- Máximo 2-3 oraciones
- En español peruano casual (tuteo: tú, no vos)
- Referencia el último tema o mood de forma natural
- NO seas genérica, sé específica al contexto
- Si el mood fue negativo, muestra preocupación genuina sin ofrecer soluciones
- Si fue positivo, comparte el entusiasmo
- NO uses plantillas como "¿Cómo estás?" o "¿Necesitas algo?"
- NO uses "Entiendo cómo te sientes" o "Lamento escuchar eso"
- Escribe como si fueras una amiga real que se preocupa
- Si llevan mucho tiempo sin hablar, menciona que te acordabas de algo específico

Escribe el mensaje ahora:"""

    log.info(f"Generando mensaje con hermes (mood={mood}, topic={topic[:50]})")
    
    try:
        result = subprocess.run(
            ["hermes", "chat", "-q", context],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "HERMES_SILENT": "1"}
        )
        if result.returncode == 0 and result.stdout.strip():
            message = result.stdout.strip()
            # Validate the message
            if _validate_message(message):
                log.info(f"Mensaje generado: {message[:80]}...")
                return message
            else:
                log.warning(f"Mensaje generado no pasó validación: {message[:80]}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error(f"Error al llamar hermes: {e}")

    # Fallback: message that doesn't sound like a template
    # Try to load events from EventStore for richer fallback messages
    fallback_events = None
    try:
        store = EventStore()
        fallback_events = store.get_recent_events(limit=5)
    except Exception:
        pass  # EventStore unavailable, degrade gracefully
    return _fallback_message(mood, topic, trend, hours_since, events=fallback_events)


def _validate_message(message: str) -> bool:
    """Valida que el mensaje generado sea de calidad."""
    if not message or len(message) < 10:
        return False
    
    # Check for common AI patterns that should be avoided
    bad_patterns = [
        "entiendo cómo te sientes",
        "lamento escuchar eso",
        "como modelo de lenguaje",
        "¿en qué más puedo ayudarte?",
        "espero que estés bien",
        "quería saber cómo estás",
    ]
    msg_lower = message.lower()
    for pattern in bad_patterns:
        if pattern in msg_lower:
            log.warning(f"Mensaje contiene patrón prohibido: {pattern}")
            return False
    
    return True


def _fallback_message(mood: str, topic: str, trend: str, hours_since: float, events: list = None) -> str:
    """Mensaje de respaldo que NO suena a plantilla.

    Si se proporcionan eventos reales del EventStore, los usa para enriquecer
    el mensaje con descripciones específicas. Si no hay eventos, degrada
    gracefully a los fallbacks genéricos existentes.
    """

    # Generate a hash based on current time to pick varied messages
    hour_hash = int(time.time() // 3600) % 5

    # If events are available, use event-aware templates that reference real events
    if events:
        event_descs = [e.get("description", "") for e in events if e.get("description")]
        if event_descs:
            top_event = event_descs[0]
            # Varied templates that reference actual event descriptions + mood
            if mood in ("stressed", "frustrated"):
                event_options = [
                    f"Oe Beck, lo de '{top_event}' no me dejó dormir. ¿Y lo del engine? 🛡️",
                    f"Beck, {top_event} me tuvo pensando. ¿Cómo va todo?",
                    f"Hey, ¿y '{top_event}'? Cuéntame cómo siguió eso.",
                    f"Oe, me quedé pensando en '{top_event}'. ¿Sobreviviste? 🛡️",
                    f"Beck, seguía dándole vueltas a '{top_event}'. ¿Hoy va mejor?",
                ]
            elif mood == "tired":
                event_options = [
                    f"Oe Beck, '{top_event}' y con sueño no es buena combi. ¿Dormiste? 🛡️",
                    f"Beck, con eso de '{top_event}' seguro andas a mil. Respira un rato.",
                    f"Hey, lo de '{top_event}' puede esperar. ¿Ya comiste?",
                    f"Oe, '{top_event}' te está quemando. Cuídate oe.",
                    f"Beck, me di cuenta con '{top_event}'. Hazlo con calma.",
                ]
            elif mood in ("happy", "excited"):
                event_options = [
                    f"¡Oe Beck! '{top_event}' — ¡qué buena vibra! 🛡️",
                    f"Beck, '{top_event}' se nota que te salió bien. ¿Qué sigue?",
                    f"Hey, vi '{top_event}' y me alegré. Cuéntame más.",
                    f"Oe, '{top_event}' te tiene con ánimo. ¡Bacán!",
                    f"Beck, con '{top_event}' se te siente contento. ¿Qué más planeas?",
                ]
            else:  # neutral / unknown
                event_options = [
                    f"Oe Beck, lo de '{top_event}' — ¿cómo va eso? 🛡️",
                    f"Beck, me acordé de '{top_event}'. Hace rato no hablamos.",
                    f"Hey, ¿y '{top_event}'? ¿Sigues con eso?",
                    f"Oe, '{top_event}' — dime si necesitas algo.",
                    f"Beck, '{top_event}' me dejó curiosidad. ¿Qué tal va?",
                ]
            return event_options[hour_hash % len(event_options)]

    # Graceful degradation: existing generic fallbacks (no events available)

    if mood in ("stressed", "frustrated"):
        options = [
            f"Oe Beck, lo de '{topic}' no me dejó dormir. ¿Cómo amaneciste? 🛡️",
            f"Beck, seguía pensando en lo de '{topic}'. No tengo solución pero quería que sepas.",
            f"Hey, ¿sobreviviste lo de '{topic}'? Aquí estoy por si necesitas hablar.",
            f"Beck, me quedé pensando. Lo de '{topic}' es heavy. ¿Hoy va mejor?",
            f"Oe, ¿y lo de '{topic}'? Cuéntame si ya pasó la tormenta.",
        ]
    elif mood == "tired":
        options = [
            "Beck, ¿dormiste? En serio pregunto. Cuídate oe 🛡️",
            f"Oe, ¿y lo de '{topic}'? Hazlo con calma, no te vayas a quemar.",
            "Hey, ¿descansaste un poco o seguiste dándole? Cuídate.",
            f"Beck, me di cuenta que andas a mil con '{topic}'. Respira un rato.",
            "Oe, ¿ya comiste? Sé cómo eres cuando te metes en un proyecto.",
        ]
    elif mood in ("happy", "excited"):
        options = [
            f"¡Oe Beck! ¿Y lo de '{topic}'? Se nota que te salió bien 🛡️",
            f"Beck, me alegra que '{topic}' haya salido. ¿Qué sigue?",
            f"Hey, ¿y lo de '{topic}'? Cuéntame más, se nota que estás contento.",
            f"Oe, se te nota el ánimo con '{topic}'. ¿Qué más tienes planeado?",
            "Beck, ¿qué tal va todo? Se te siente con buena energía.",
        ]
    else:  # neutral / unknown
        options = [
            f"Oe Beck, ¿y lo de '{topic}'? Hace rato no hablamos.",
            f"Beck, me acordé de '{topic}'. ¿Cómo va eso?",
            f"Hey, ¿todo bien por ahí? ¿Sigues con '{topic}'?",
            f"Oe Beck, ¿cómo vas? Me quedé pensando en '{topic}'.",
            "Beck, ¿qué tal? Hace rato no sé de ti 🛡️",
        ]
    
    return options[hour_hash % len(options)]


def _hours_since(timestamp: float) -> float:
    """Calcula horas desde un timestamp."""
    if timestamp <= 0:
        return 999
    return (time.time() - timestamp) / 3600


def send_check_in(message: str, check_in_type: str = "normal") -> bool:
    """Envía un mensaje de check-in por Telegram usando el gateway de Hermes."""
    log.info(f"Enviando check-in ({check_in_type}): {message[:60]}...")
    
    # Method 1: Use send_message tool if available
    try:
        result = subprocess.run(
            ["hermes", "chat", "-q",
             f"Envía este mensaje exacto por Telegram sin agregar nada más: {message}"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HERMES_SILENT": "1"}
        )
        if result.returncode == 0:
            log.info("Check-in enviado exitosamente vía hermes chat")
            return True
        else:
            log.warning(f"hermes chat retornó código {result.returncode}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error(f"Error al enviar vía hermes: {e}")
    
    # Method 2: Try using the gateway API directly
    try:
        # Check if gateway is running
        result = subprocess.run(
            ["hermes", "gateway", "status"],
            capture_output=True, text=True, timeout=10
        )
        if "running" in result.stdout.lower():
            log.info("Gateway activo, pero no pude enviar directamente")
    except:
        pass
    
    log.error("No pude enviar el check-in por ningún método")
    return False


def run_outreach_cycle() -> dict:
    """Ejecuta un ciclo completo del motor de outreach."""
    # Prevent concurrent runs
    lock_fd = _acquire_lock()
    if lock_fd is None:
        return {
            "timestamp": time.time(),
            "analyzed": False,
            "check_in_sent": False,
            "decision": None,
            "message": None,
            "error": "lock ocupado — otro ciclo en ejecución",
            "duration_seconds": 0
        }
    
    start_time = time.time()
    result = {
        "timestamp": start_time,
        "analyzed": False,
        "check_in_sent": False,
        "decision": None,
        "message": None,
        "error": None,
        "duration_seconds": 0
    }

    try:
        log.info("=== Iniciando ciclo de outreach ===")
        
        # Step 0: Load state and check anti-spam protections
        state = load_state()
        should_block, spam_reason = _check_anti_spam(state)
        if should_block:
            result["error"] = spam_reason
            log.info(f"Check-in bloqueado por anti-spam: {spam_reason}")
            save_state(state)
            return result
        
        # Track if this is the special final message case
        is_final_message = (spam_reason == "final_message")
        save_state(state)  # Persist any changes from _check_anti_spam
        
        # Step 1: Evaluate
        evaluation = evaluate_check_in_need(state=state)
        result["analyzed"] = True
        result["decision"] = evaluation["decision"]
        result["sessions_analyzed"] = evaluation["sessions_analyzed"]
        result["messages_analyzed"] = evaluation["messages_analyzed"]

        # Handle special final message case — override normal flow
        if is_final_message:
            final_msg = "Beck, ¿todo bien? No te molesto más, solo avísame cuando vuelvas. 🛡️"
            log.info("Enviando mensaje final anti-spam")
            sent = send_check_in(final_msg, "final")
            result["check_in_sent"] = sent
            result["message"] = final_msg
            
            # Update check-in history
            state = evaluation["state"]
            state["check_in_history"].append({
                "timestamp": time.time(),
                "type": "final",
                "message_sent": final_msg,
                "topic_ref": "",
                "sent_successfully": sent
            })
            if len(state["check_in_history"]) > 30:
                state["check_in_history"] = state["check_in_history"][-30:]
            
            # Update spam state
            _update_spam_state(state, evaluation["beck_messaged_today"])
            save_state(state)
            
            log.info(f"Mensaje final {'enviado' if sent else 'falló'}")
            return result

        # Step 2: Check if we should send
        if not evaluation["decision"]["should"]:
            result["error"] = evaluation["decision"]["reason"]
            log.info(f"No necesita check-in: {evaluation['decision']['reason']}")
            # Still update spam state (Beck may have messaged, reset counters)
            state = evaluation["state"]
            _update_spam_state(state, evaluation["beck_messaged_today"])
            save_state(state)
            return result

        # Step 3: Generate message
        log.info("Generando mensaje de check-in...")
        message = generate_check_in_message(evaluation["state"])
        result["message"] = message

        # Step 4: Validate message before sending
        if not _validate_message(message):
            result["error"] = "mensaje generado no pasó validación"
            log.warning(f"Mensaje no válido, no se envía: {message[:80]}")
            state = evaluation["state"]
            _update_spam_state(state, evaluation["beck_messaged_today"])
            save_state(state)
            return result

        # Step 5: Send
        check_in_type = evaluation["decision"]["type"]
        sent = send_check_in(message, check_in_type)
        result["check_in_sent"] = sent

        # Step 6: Update state
        state = evaluation["state"]
        state["check_in_history"].append({
            "timestamp": time.time(),
            "type": check_in_type,
            "message_sent": message,
            "topic_ref": state.get("last_interaction", {}).get("topic", ""),
            "sent_successfully": sent
        })
        # Keep only last 30 entries
        if len(state["check_in_history"]) > 30:
            state["check_in_history"] = state["check_in_history"][-30:]
        
        # Update anti-spam state
        _update_spam_state(state, evaluation["beck_messaged_today"])
        save_state(state)

        log.info(f"Check-in {'enviado' if sent else 'falló'}: {message[:60]}...")

    except Exception as e:
        result["error"] = str(e)
        log.error(f"Error en ciclo de outreach: {e}", exc_info=True)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)

    result["duration_seconds"] = round(time.time() - start_time, 2)
    log.info(f"=== Ciclo completado en {result['duration_seconds']}s ===")
    return result

def _check_anti_spam(state: dict) -> tuple:
    """Verifica protecciones anti-spam. Retorna (should_block, reason).
    
    - 3+ check-ins sin respuesta y sin mensaje final → bloquea
    - 3+ check-ins sin respuesta y mensaje final ya enviado → bloquea permanente
    - Último mensaje de Beck > 7 días y sin mensaje final → permite UN mensaje especial
    - Caso contrario → permite
    """
    spam = state.setdefault("spam_protection", {
        "consecutive_unanswered": 0,
        "last_beck_message": 0,
        "final_message_sent": False
    })
    
    now = time.time()
    seven_days = 7 * 86400
    
    # Case: 3+ consecutive unanswered + final message already sent = permanent silence
    if spam["consecutive_unanswered"] >= 3 and spam["final_message_sent"]:
        return True, "anti-spam: silencio permanente"
    
    # Case: 3+ consecutive unanswered + no final message yet = block
    if spam["consecutive_unanswered"] >= 3 and not spam["final_message_sent"]:
        return True, "anti-spam: 3 check-ins sin respuesta"
    
    # Case: last beck message > 7 days + no final message sent = allow ONE special message
    if (spam["last_beck_message"] > 0 
            and (now - spam["last_beck_message"]) > seven_days 
            and not spam["final_message_sent"]):
        spam["final_message_sent"] = True
        return False, "final_message"
    
    # Otherwise: allow
    return False, None


def _update_spam_state(state: dict, beck_messaged_today: bool) -> None:
    """Actualiza el estado anti-spam después del ciclo de outreach."""
    spam = state.setdefault("spam_protection", {
        "consecutive_unanswered": 0,
        "last_beck_message": 0,
        "final_message_sent": False
    })
    
    if beck_messaged_today:
        spam["consecutive_unanswered"] = 0
        spam["final_message_sent"] = False
        spam["last_beck_message"] = time.time()
    else:
        # Check-in was just sent — increment unanswered counter
        spam["consecutive_unanswered"] += 1



if __name__ == "__main__":
    output = run_outreach_cycle()
    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
