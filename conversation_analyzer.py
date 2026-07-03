"""
conversation_analyzer.py — Analiza conversaciones recientes de ~/.hermes/state.db
Detecta emociones, patrones y eventos significativos.
"""
import sqlite3
import time
import re
from pathlib import Path
from collections import Counter

DB_PATH = Path.home() / ".hermes" / "state.db"

# System message prefixes — these are NOT real user messages
SYSTEM_MESSAGE_PREFIXES = [
    "[IMPORTANT:",
    "[OUT-OF-BAND",
    "[ASYNC DELEGATION",
    "Eres Ivi",
    "You are",
    "Cronjob Response:",
    "[Replying to:"
]

SYSTEM_MESSAGE_CONTAINS = [
    "Cronjob Response",
    "ASYNC DELEGATION BATCH COMPLETE",
    "The user has invoked",
    "Read arxiv abstract",
    "extract autonomous",
    "You are running as a scheduled cron",
    "DELIVER",
    "hermes chat -q",
    "tool_calls",
    "function_call",
    "Background process",
    "terminated by process.kill",
    "OUT-OF-BAND USER MESSAGE",
    "[IMPORTANT",
    "Exit code",
    "Command:",
    "notify_on_complete",
    "session_id",
    "hermes_results",
]


def _is_system_message(content: str) -> bool:
    """Detecta si un mensaje es del sistema/asistente, no del usuario real."""
    if not content:
        return True
    for prefix in SYSTEM_MESSAGE_PREFIXES:
        if content.startswith(prefix):
            return True
    for pattern in SYSTEM_MESSAGE_CONTAINS:
        if pattern in content:
            return True
    return False


# Mood keyword definitions (Peruvian Spanish)
MOOD_KEYWORDS = {
    "stressed": [
        "no puedo", "imposible", "ya fue", "qué mierda", "agotado",
        "estresado", "no doy más", "qué estrés", "estoy mal", "reventado",
        "colapsado", "no aguanto", "presión", "deadline"
    ],
    "happy": [
        "genial", "perfecto", "funcionó", "logré", "bien hecho",
        "excelente", "qué bien", "increíble", "fantástico",
        "super", "felicidades", "alegre", "feliz", "contento",
        "maravilloso", "estupendo", "magnífico"
    ],
    "tired": [
        "cansado", "madrugada", "no duermo", "sueño", "dormido",
        "agotado", "sin energía", "flojera", "modorra", "somnoliento",
        "desvelado", "noche"
    ],
    "frustrated": [
        "otra vez", "no funciona", "error", "falla", "falló", "fallo", "bug",
        "maldita sea", "qué fastidio", "no sirve", "basura", "inútil",
        "frustrado", "harto", "ya basta"
    ],
    "excited": [
        "increíble", "wow", "no manches", "alucinante", "brutal",
        "qué locura", "impresionante", "cool", "top", "increible",
        "asombroso", "fantástico", "qué crack", "vamos"
    ]
}


def get_recent_sessions(hours: int = 48) -> list[dict]:
    """Obtiene sesiones recientes con sus mensajes del state.db."""
    cutoff = time.time() - (hours * 3600)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id as session_id, s.started_at, s.title, s.source
        FROM sessions s
        WHERE s.started_at >= ? AND s.archived = 0
        ORDER BY s.started_at DESC
    """, (cutoff,))
    sessions = [dict(row) for row in cursor.fetchall()]

    for session in sessions:
        cursor.execute("""
            SELECT role, content, timestamp
            FROM messages
            WHERE session_id = ? AND active = 1 AND content IS NOT NULL
            ORDER BY timestamp ASC
        """, (session["session_id"],))
        session["messages"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return sessions


def extract_emotional_keywords(text: str) -> dict[str, list[str]]:
    """Extrae keywords emocionales de un texto. Retorna dict con mood -> lista de keywords encontrados."""
    if not text:
        return {}
    text_lower = text.lower()
    found = {}
    for mood, keywords in MOOD_KEYWORDS.items():
        matches = [kw for kw in keywords if kw in text_lower]
        if matches:
            found[mood] = matches
    return found


def analyze_conversation_mood(messages: list[dict]) -> dict:
    """Analiza el mood general de una conversación basado en keywords."""
    mood_scores = Counter()
    total_user_msgs = 0
    msgs_with_keywords = 0
    now = time.time()

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content or _is_system_message(content):
            continue
        total_user_msgs += 1
        keywords = extract_emotional_keywords(content)
        if keywords:
            msgs_with_keywords += 1

        # Recency weighting: weight = 0.5 ** (age_hours / 12)
        ts = msg.get("timestamp", 0)
        if ts and ts > 0:
            age_hours = max(0, (now - ts) / 3600)
            recency_weight = 0.5 ** (age_hours / 12)
        else:
            recency_weight = 1.0

        for mood, matches in keywords.items():
            # Weight: repeated keywords in same message = higher intensity
            weight = len(matches) * (1 + 0.5 * (len(matches) - 1))
            mood_scores[mood] += weight * recency_weight

    if not mood_scores:
        return {"mood": "neutral", "intensity": 0.0, "scores": {}}

    dominant_mood = mood_scores.most_common(1)[0][0]
    max_score = mood_scores.most_common(1)[0][1]
    # Intensity = density of emotional keywords in messages that HAVE them
    # This rewards concentrated emotion vs scattered keywords
    intensity = min(1.0, max_score / max(msgs_with_keywords, 1) * 0.4)

    return {
        "mood": dominant_mood,
        "intensity": round(intensity, 2),
        "scores": dict(mood_scores)
    }


def analyze_mood_v3(messages: list[dict], detector=None) -> dict:
    """v3.0: Analyze conversation mood using EmotionDetector (Strategy pattern).

    Falls back to keyword-based analyze_conversation_mood() if no detector provided.
    Returns same dict format for backward compatibility.
    """
    if detector is None:
        return analyze_conversation_mood(messages)

    result = detector.detect_conversation(messages, recency_weighted=True)
    return {
        "mood": result.mood,
        "intensity": result.intensity,
        "scores": result.scores,
        "confidence": result.confidence,
        "source": result.source,
        "is_ironic": result.is_ironic,
    }


def detect_significant_events(messages: list[dict]) -> list[dict]:
    """Detecta eventos significativos en una conversación."""
    events = []
    seen_late_night = set()
    bad_moods = {"stressed", "frustrated", "tired"}

    # Patterns for emotional declarations, worries, celebrations, vulnerability
    emotional_declaration_re = re.compile(
        r"estoy (contento|triste|feliz|enojado|furioso|estresado|asustado|preocupado|ansioso|deprimido|mal|bien|agotado|cansado|frustrado)"
        r"|me siento (contento|triste|feliz|enojado|furioso|estresado|asustado|preocupado|ansioso|deprimido|mal|bien|agotado|cansado|frustrado|solo|perdido)",
        re.IGNORECASE
    )
    worry_re = re.compile(
        r"me preocupa|tengo miedo de|no sé si|me da miedo|estoy preocupado",
        re.IGNORECASE
    )
    celebration_re = re.compile(
        r"lo logré|funcionó|por fin|lo conseguí|ya quedó|ya está listo",
        re.IGNORECASE
    )
    vulnerability_re = re.compile(
        r"necesito ayuda|no sé qué hacer|estoy perdido|no sé qué hacer|no aguanto más",
        re.IGNORECASE
    )

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content or _is_system_message(content):
            continue

        keywords = extract_emotional_keywords(content)
        ts = msg.get("timestamp", 0)

        # Detect late night activity (deduplicate by hour)
        if ts:
            hour = int(time.strftime("%H", time.localtime(ts)))
            if hour >= 1 and hour <= 5:
                # Only add one late_night event per hour
                hour_key = f"late_night_{hour}_{int(ts // 3600)}"
                if hour_key not in seen_late_night:
                    seen_late_night.add(hour_key)
                    events.append({
                        "timestamp": ts,
                        "type": "late_night",
                        "description": f"Actividad a las {hour}:00",
                        "mood": "tired"
                    })

        # Detect stress/frustration spikes
        for mood in bad_moods:
            if mood in keywords and len(keywords[mood]) >= 2:
                events.append({
                    "timestamp": ts,
                    "type": "stress_spike",
                    "description": f"Múltiples indicadores de {mood}: {', '.join(keywords[mood])}",
                    "mood": mood
                })

        # Detect achievements (only from REAL user messages with clear emotional content)
        if ("happy" in keywords or "excited" in keywords) and len(content) > 20:
            events.append({
                "timestamp": ts,
                "type": "achievement",
                "description": f"Logro detectado: {content[:80]}",
                "mood": keywords.get("happy", keywords.get("excited", ["happy"]))[0]
            })

        # Detect direct emotional declarations
        if emotional_declaration_re.search(content):
            events.append({
                "timestamp": ts,
                "type": "emotional_declaration",
                "description": f"Declaración emocional: {content[:80]}",
                "mood": "emotional"
            })

        # Detect worries
        if worry_re.search(content):
            events.append({
                "timestamp": ts,
                "type": "worry",
                "description": f"Preocupación detectada: {content[:80]}",
                "mood": "stressed"
            })

        # Detect celebrations
        if celebration_re.search(content):
            events.append({
                "timestamp": ts,
                "type": "celebration",
                "description": f"Celebración: {content[:80]}",
                "mood": "happy"
            })

        # Detect vulnerability
        if vulnerability_re.search(content):
            events.append({
                "timestamp": ts,
                "type": "vulnerability",
                "description": f"Vulnerabilidad: {content[:80]}",
                "mood": "stressed"
            })

    return events


def detect_communication_patterns(messages: list[dict]) -> dict:
    """Detecta patrones de comunicación: horarios, longitud, temas."""
    user_messages = [m for m in messages
                     if m.get("role") == "user"
                     and m.get("content")
                     and not _is_system_message(m.get("content", ""))]

    if not user_messages:
        return {
            "active_hours": {"start": 8, "end": 23},
            "avg_message_length": 0,
            "common_topics": [],
            "response_pattern": "normal"
        }

    # Active hours
    hours = []
    lengths = []
    for msg in user_messages:
        ts = msg.get("timestamp", 0)
        if ts:
            hours.append(int(time.strftime("%H", time.localtime(ts))))
        content = msg.get("content", "")
        lengths.append(len(content))

    # Topic extraction (simple: find common long words)
    all_text = " ".join(m.get("content", "") for m in user_messages).lower()
    words = re.findall(r'\b[a-záéíóúñ]{5,}\b', all_text)
    stopwords = {"puede", "tiene", "hacer", "donde", "cuando", "porque", "pero",
                 "como", "esta", "estos", "estas", "para", "todo", "bien",
                 "hola", "sobre", "también", "entre", "otro", "otra", "desde"}
    topic_words = [w for w in words if w not in stopwords]
    common_topics = [w for w, _ in Counter(topic_words).most_common(5)]

    active_start = min(hours) if hours else 8
    active_end = max(hours) if hours else 23
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # Response pattern (simplified: based on message count)
    msg_count = len(user_messages)
    if msg_count > 20:
        pattern = "quick"
    elif msg_count > 5:
        pattern = "normal"
    else:
        pattern = "slow"

    return {
        "active_hours": {"start": active_start, "end": active_end},
        "avg_message_length": round(avg_length, 1),
        "common_topics": common_topics,
        "response_pattern": pattern
    }
