#!/usr/bin/env python3
"""
daemon.py — Cosmo Watcher Daemon
Monitorea state.db por nuevos mensajes, detecta emociones con Cosmo,
y dispara check-ins via Hermes cuando es necesario.

Uso:
    python3 daemon.py                  # Foreground
    python3 daemon.py --interval 15    # Polling cada 15s
    python3 daemon.py --dry-run        # No ejecutar check-ins reales

Requiere:
    - psutil (para memory monitoring)
    - pysentimiento (en .venv/)
    - hermes CLI en PATH

Archivo de estado: ~/.hermes/daemon-state.json
PID file: /tmp/cosmo-watcher.pid
Logs: ~/.hermes/logs/cosmo-watcher.log
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import psutil

# ── Paths ─────────────────────────────────────────────────────────
ENGINE_DIR = Path(__file__).parent
HERMES_DIR = Path.home() / ".hermes"
DB_PATH = HERMES_DIR / "state.db"
DAEMON_STATE_PATH = HERMES_DIR / "daemon-state.json"
PID_FILE = Path("/tmp/cosmo-watcher.pid")
LOG_DIR = HERMES_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL = 15  # seconds
RAM_THRESHOLD_PERCENT = 85  # unload model if RAM > 85%
HERMES_TIMEOUT = 120        # seconds
WATCHDOG_INTERVAL = 60      # seconds (must be < systemd WatchdogSec)
MODEL_RELOAD_COOLDOWN = 300 # seconds before reloading after unload

# ── Logging ───────────────────────────────────────────────────────
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure rotating file + stderr logging."""
    logger = logging.getLogger("cosmo-watcher")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Rotating file handler
    fh = RotatingFileHandler(
        LOG_DIR / "cosmo-watcher.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    # Stderr handler (for systemd journal)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(sh)

    return logger


log = setup_logging()


# ── Daemon State Persistence ──────────────────────────────────────

def load_daemon_state() -> dict:
    """Load persistent daemon state from JSON."""
    default = {
        "last_processed_id": 0,
        "last_cycle_time": 0.0,
        "cycles_completed": 0,
        "errors_count": 0,
        "last_error": None,
        "started_at": 0.0,
    }
    if DAEMON_STATE_PATH.exists():
        try:
            data = json.loads(DAEMON_STATE_PATH.read_text())
            # Merge with defaults for forward compatibility
            for k, v in default.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_daemon_state(state: dict) -> None:
    """Persist daemon state to JSON."""
    DAEMON_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_STATE_PATH.write_text(
        json.dumps(state, indent=2, default=str)
    )


# ── PID File Management ──────────────────────────────────────────

def write_pid() -> None:
    """Write current PID. Raises if another daemon is alive."""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)  # Check if alive
            raise RuntimeError(
                f"Daemon ya corriendo (PID {old_pid}). "
                f"Kill it first: kill {old_pid}"
            )
        except (ProcessLookupError, ValueError):
            pass  # Dead PID, we can proceed
    PID_FILE.write_text(str(os.getpid()))


def cleanup_pid() -> None:
    """Remove PID file on exit."""
    PID_FILE.unlink(missing_ok=True)


# ── Memory Monitoring ─────────────────────────────────────────────

def get_memory_info() -> dict:
    """Return memory usage stats."""
    mem = psutil.virtual_memory()
    return {
        "total_mb": mem.total // (1024 * 1024),
        "used_mb": mem.used // (1024 * 1024),
        "available_mb": mem.available // (1024 * 1024),
        "percent": mem.percent,
    }


# ── Singleton Detector ────────────────────────────────────────────

class DetectorManager:
    """Manages the HybridDetector singleton with memory-aware unloading."""

    def __init__(self):
        self._detector = None
        self._loaded_at = 0.0
        self._unloaded_at = 0.0
        self._lock = threading.Lock()

    def get(self):
        """Get or create the detector. Returns None if memory is too high."""
        with self._lock:
            # Check if we're in cooldown after unload
            if self._unloaded_at > 0:
                elapsed = time.time() - self._unloaded_at
                if elapsed < MODEL_RELOAD_COOLDOWN:
                    log.debug(
                        f"Modelo en cooldown ({MODEL_RELOAD_COOLDOWN - elapsed:.0f}s restantes)"
                    )
                    return None

            # Check memory before loading
            mem = psutil.virtual_memory()
            if mem.percent > RAM_THRESHOLD_PERCENT:
                log.warning(
                    f"RAM al {mem.percent}% — no cargando modelo "
                    f"(threshold: {RAM_THRESHOLD_PERCENT}%)"
                )
                return None

            # Load if needed
            if self._detector is None:
                log.info("Cargando HybridDetector (Cosmo + keyword)...")
                try:
                    # Add engine dir to path for imports
                    if str(ENGINE_DIR) not in sys.path:
                        sys.path.insert(0, str(ENGINE_DIR))
                    from emotion_detector import HybridDetector
                    self._detector = HybridDetector()
                    self._loaded_at = time.time()
                    log.info("HybridDetector cargado exitosamente")
                except Exception as e:
                    log.error(f"Error cargando detector: {e}")
                    self._detector = None

            return self._detector

    def unload(self, reason: str = "") -> None:
        """Force unload the model to free RAM."""
        with self._lock:
            if self._detector is not None:
                log.warning(f"Descargando modelo: {reason}")
                self._detector = None
                self._unloaded_at = time.time()
                gc.collect()

    def maybe_unload(self) -> bool:
        """Unload if memory pressure is high. Returns True if unloaded."""
        mem = psutil.virtual_memory()
        if mem.percent > RAM_THRESHOLD_PERCENT:
            self.unload(f"RAM al {mem.percent}%")
            return True
        return False

    @property
    def is_loaded(self) -> bool:
        return self._detector is not None


# ── Database Polling ──────────────────────────────────────────────

def fetch_new_messages(last_id: int) -> list[dict]:
    """Fetch user messages with id > last_id from state.db."""
    if not DB_PATH.exists():
        return []

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT m.id, m.session_id, m.role, m.content, m.timestamp, s.source
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE m.id > ?
              AND m.role = 'user'
              AND m.active = 1
              AND m.content IS NOT NULL
              AND s.archived = 0
            ORDER BY m.id ASC
            LIMIT 50
        """, (last_id,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        log.error(f"SQLite error: {e}")
        return []


def get_max_message_id() -> int:
    """Get the current maximum message id."""
    if not DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM messages")
        result = cursor.fetchone()[0]
        conn.close()
        return result
    except sqlite3.Error:
        return 0


# ── Emotion Processing ────────────────────────────────────────────

def is_system_message(content: str) -> bool:
    """Check if a message is from the system, not the real user."""
    if not content or len(content.strip()) < 3:
        return True

    # Prefixes that indicate system messages
    prefixes = [
        "[IMPORTANT:", "[OUT-OF-BAND", "[ASYNC DELEGATION", "Eres Ivi",
        "You are", "Cronjob Response:", "[Replying to:", "[IMPORTANT",
    ]
    if any(content.startswith(p) for p in prefixes):
        return True

    # Patterns that indicate system messages (anywhere in content)
    contains = [
        "Cronjob Response", "ASYNC DELEGATION BATCH COMPLETE",
        "The user has invoked", "Read arxiv abstract",
        "extract autonomous", "You are running as a scheduled cron",
        "Background process", "terminated by process.kill",
        "Exit code", "notify_on_complete", "session_id",
        "hermes_results", "OUT-OF-BAND USER MESSAGE",
        "Command:", "tool_calls", "function_call",
        "Warning: Unknown toolsets", "hermes chat -q",
        "DELIVER",
    ]
    if any(p in content for p in contains):
        return True

    return False


def analyze_messages(messages: list[dict], detector_manager: DetectorManager) -> dict:
    """Analyze new messages for emotional content."""
    if not messages:
        return {"mood": "neutral", "intensity": 0.0, "events": []}

    # Filter to real user messages only
    user_msgs = [
        m for m in messages
        if m.get("role") == "user"
        and not is_system_message(m.get("content", ""))
    ]

    if not user_msgs:
        return {"mood": "neutral", "intensity": 0.0, "events": []}

    detector = detector_manager.get()

    if detector is not None:
        # Use Cosmo/HybridDetector
        try:
            result = detector.detect_conversation(
                user_msgs, recency_weighted=True
            )
            return {
                "mood": result.mood,
                "intensity": result.intensity,
                "confidence": result.confidence,
                "source": result.source,
                "events": [],
            }
        except Exception as e:
            log.warning(f"Detector error, falling back to keywords: {e}")

    # Fallback: keyword-based detection
    try:
        if str(ENGINE_DIR) not in sys.path:
            sys.path.insert(0, str(ENGINE_DIR))
        from conversation_analyzer import analyze_conversation_mood
        return analyze_conversation_mood(user_msgs)
    except ImportError:
        return {"mood": "neutral", "intensity": 0.0, "events": []}


# ── Check-in Decision ─────────────────────────────────────────────

def should_do_checkin(messages: list[dict], mood_analysis: dict) -> dict:
    """Decide if we should trigger a check-in based on new messages."""
    try:
        if str(ENGINE_DIR) not in sys.path:
            sys.path.insert(0, str(ENGINE_DIR))
        from emotional_state import load_state, should_check_in

        state = load_state()
        decision = should_check_in(state, recent_messages=messages)
        return decision
    except Exception as e:
        log.error(f"Error evaluando check-in: {e}")
        return {"should": False, "reason": f"error: {e}"}


# ── Hermes Trigger ────────────────────────────────────────────────

def generate_checkin_message(mood_analysis: dict, messages: list[dict]) -> str:
    """Generate a natural check-in message based on detected mood.

    Messages are conversational and don't quote the user's text back at them.
    No LLM needed — zero tokens, instant delivery.
    """
    mood = mood_analysis.get("mood", "neutral")

    # Natural, conversational templates per mood (neutral Spanish)
    # These DON'T repeat what the user said — they acknowledge the emotion
    templates = {
        "stressed": [
            "Beck, se nota que andas con presión. ¿Cómo vas?",
            "Beck, respira un momento. Las cosas se ven mejor cuando bajas un cambio.",
            "Beck, descansa si puedes. No todo tiene que ser hoy.",
        ],
        "frustrated": [
            "Beck, esas cosas cansan. ¿Necesitas que revisemos algo juntos?",
            "Beck, ya va a pasar. ¿Quieres que te ayude con algo?",
            "Beck, entiendo la frustración. Aquí estoy si necesitas.",
        ],
        "sad": [
            "Beck, aquí estoy si necesitas hablar. Sin presión.",
            "Beck, a veces solo saber que alguien te escucha ayuda.",
            "Beck, no tienes que cargar solo con eso.",
        ],
        "tired": [
            "Beck, ¿dormiste bien? Cuídate.",
            "Beck, el cansancio se acumula. ¿Pausaste un rato hoy?",
            "Beck, descansa si puedes. El servidor puede esperar.",
        ],
        "happy": [
            "¡Beck! Me gusta cuando andas así de animado.",
            "¡Beck! Qué bueno que andas con buena energía.",
            "¡Beck! Se nota el ánimo. Disfruta.",
        ],
        "anxious": [
            "Beck, ¿todo bien? Si algo te preocupa, aquí estoy.",
            "Beck, la incertidumbre es difícil. ¿Quieres que revisemos algo?",
            "Beck, paso a paso. ¿En qué te puedo ayudar?",
        ],
        "surprised": [
            "¡Beck! Eso suena inesperado. ¿Qué pasó?",
            "¡Beck! No me lo esperaba. Cuéntame más.",
        ],
    }

    import random
    mood_templates = templates.get(mood, [
        "Beck, ¿cómo estás? Hace rato no hablamos."
    ])
    return random.choice(mood_templates)


def deliver_checkin(message: str, dry_run: bool = False) -> bool:
    """Deliver the check-in directly to Telegram via hermes send."""
    if dry_run:
        log.info(f"[DRY-RUN] Check-in: {message}")
        return True

    log.info(f"Entregando check-in: {message[:80]}...")
    try:
        # Clean environment: remove cron session flag so hermes send works
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ('HERMES_CRON_SESSION',)}
        
        result = subprocess.run(
            ["hermes", "send", "-t", "telegram", "-q", message],
            capture_output=True, text=True, timeout=30,
            env=clean_env
        )
        if result.returncode == 0:
            log.info("Check-in entregado exitosamente via hermes send")
            return True
        log.warning(f"Entrega falló: rc={result.returncode} stderr={result.stderr[:200]}")
    except Exception as e:
        log.error(f"Error entregando check-in: {e}")
    return False


# ── systemd Integration ──────────────────────────────────────────

def sd_notify(message: str) -> None:
    """Send notification to systemd via NOTIFY_SOCKET."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    try:
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        sock.sendto(message.encode(), addr)
        sock.close()
    except Exception:
        pass  # Not running under systemd, that's fine


def sd_watchdog_ping() -> None:
    """Send watchdog keepalive to systemd."""
    sd_notify("WATCHDOG=1")


def sd_ready() -> None:
    """Notify systemd that the daemon is ready."""
    sd_notify("READY=1")


# ── Main Daemon Loop ─────────────────────────────────────────────

class CosmoWatcherDaemon:
    """Main daemon class — orchestrates polling, detection, and delivery."""

    def __init__(self, interval: int = DEFAULT_POLL_INTERVAL, dry_run: bool = False):
        self.interval = interval
        self.dry_run = dry_run
        self.shutdown_event = threading.Event()
        self.detector_manager = DetectorManager()
        self.state = load_daemon_state()
        self._last_watchdog_ping = 0.0
        self._checkin_cooldown_until = 0.0  # Don't check-in again until this time

    def setup_signals(self) -> None:
        """Register signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        signal.signal(signal.SIGHUP, self._handle_sighup)

    def _handle_sigterm(self, signum, frame):
        log.info(f"Señal {signum} recibida — cerrando daemon")
        self.shutdown_event.set()

    def _handle_sighup(self, signum, frame):
        log.info("SIGHUP recibido — recargando configuración")
        # Reload config.py if it changed
        try:
            if str(ENGINE_DIR) in sys.path:
                import importlib
                import config as engine_config
                importlib.reload(engine_config)
                log.info("Config recargada")
        except Exception as e:
            log.warning(f"Error recargando config: {e}")

    def _maybe_ping_watchdog(self) -> None:
        """Ping systemd watchdog if enough time has passed."""
        now = time.time()
        if now - self._last_watchdog_ping >= WATCHDOG_INTERVAL:
            sd_watchdog_ping()
            self._last_watchdog_ping = now

    def _process_new_messages(self, messages: list[dict]) -> None:
        """Process newly detected messages."""
        # Filter out system messages immediately
        real_messages = [m for m in messages if not is_system_message(m.get("content", ""))]
        if not real_messages:
            log.info(f"Filtrados {len(messages)} mensajes (todos eran del sistema)")
            return

        if len(real_messages) < len(messages):
            log.info(f"Filtrados {len(messages) - len(real_messages)} mensajes del sistema, {len(real_messages)} reales")

        log.info(f"Procesando {len(real_messages)} mensajes nuevos")

        # 1. Analyze emotions
        mood_analysis = self.analyze_messages(real_messages)
        mood = mood_analysis.get("mood", "neutral")
        intensity = mood_analysis.get("intensity", 0.0)
        log.info(f"Emoción detectada: {mood} (intensidad: {intensity:.2f})")

        # 2. Check if we should do a check-in (with cooldown)
        now = time.time()
        if now < self._checkin_cooldown_until:
            remaining = self._checkin_cooldown_until - now
            log.info(f"Cooldown activo ({remaining:.0f}s restantes)")
            return

        # 3. Evaluate check-in need
        decision = self.should_do_checkin(real_messages, mood_analysis)
        log.info(f"Decisión check-in: {decision}")

        if decision.get("should"):
            # 4. Generate and deliver message
            message = self.generate_checkin_message(mood_analysis, real_messages)
            success = self.deliver_checkin(message)

            if success:
                # Set cooldown (minimum 2 hours between check-ins from daemon)
                from config import RATE_LIMIT_CONCERNED, RATE_LIMIT_NORMAL
                bad_moods = {"stressed", "frustrated", "tired"}
                cooldown = RATE_LIMIT_CONCERNED if mood in bad_moods else RATE_LIMIT_NORMAL
                self._checkin_cooldown_until = now + cooldown
                log.info(f"Próximo check-in posible en {cooldown / 3600:.1f}h")

    def analyze_messages(self, messages: list[dict]) -> dict:
        """Analyze messages for emotional content."""
        return analyze_messages(messages, self.detector_manager)

    def should_do_checkin(self, messages: list[dict], mood_analysis: dict) -> dict:
        """Decide if a check-in is needed."""
        return should_do_checkin(messages, mood_analysis)

    def generate_checkin_message(self, mood_analysis: dict, messages: list[dict]) -> str:
        """Generate check-in message."""
        return generate_checkin_message(mood_analysis, messages)

    def deliver_checkin(self, message: str) -> bool:
        """Deliver the check-in."""
        return deliver_checkin(message, dry_run=self.dry_run)

    def run(self) -> int:
        """Main daemon loop. Returns exit code."""
        log.info("=" * 60)
        log.info("Cosmo Watcher Daemon iniciando")
        log.info(f"Intervalo: {self.interval}s | Dry-run: {self.dry_run}")
        log.info(f"DB: {DB_PATH}")
        log.info(f"RAM: {get_memory_info()}")
        log.info("=" * 60)

        # Setup
        self.setup_signals()

        try:
            write_pid()
        except RuntimeError as e:
            log.error(str(e))
            return 1

        # Initialize state
        self.state["started_at"] = time.time()
        self.state["last_cycle_time"] = 0.0
        save_daemon_state(self.state)

        # Pre-warm: skip to current max id on first run
        if self.state["last_processed_id"] == 0:
            current_max = get_max_message_id()
            if current_max > 0:
                self.state["last_processed_id"] = current_max
                save_daemon_state(self.state)
                log.info(f"Pre-warm: saltando a message id {current_max}")

        # Notify systemd we're ready
        sd_ready()
        self._last_watchdog_ping = time.time()

        log.info("Daemon listo — comenzando loop de polling")

        # Main loop
        try:
            while not self.shutdown_event.is_set():
                self._loop_iteration()
                self._maybe_ping_watchdog()

                # Wait for next cycle or shutdown
                self.shutdown_event.wait(timeout=self.interval)

        except Exception as e:
            log.error(f"Error fatal en main loop: {e}", exc_info=True)
            self.state["errors_count"] += 1
            self.state["last_error"] = str(e)
            save_daemon_state(self.state)
            return 1

        finally:
            log.info("Cerrando daemon...")
            save_daemon_state(self.state)
            cleanup_pid()
            log.info("Daemon cerrado limpiamente")

        return 0

    def _loop_iteration(self) -> None:
        """Single iteration of the polling loop."""
        try:
            # Check memory pressure
            self.detector_manager.maybe_unload()

            # Fetch new messages
            last_id = self.state["last_processed_id"]
            new_messages = fetch_new_messages(last_id)

            if new_messages:
                # Process them
                self._process_new_messages(new_messages)

                # Update offset
                max_id = max(m["id"] for m in new_messages)
                self.state["last_processed_id"] = max_id

            # Update cycle stats
            self.state["last_cycle_time"] = time.time()
            self.state["cycles_completed"] += 1
            save_daemon_state(self.state)

        except Exception as e:
            log.error(f"Error en iteración: {e}", exc_info=True)
            self.state["errors_count"] += 1
            self.state["last_error"] = str(e)
            save_daemon_state(self.state)


# ── CLI ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cosmo Watcher Daemon — Emotional awareness daemon for Hermes"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int, default=DEFAULT_POLL_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL})"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Don't actually deliver check-ins"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show daemon status and exit"
    )

    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        for handler in log.handlers:
            handler.setLevel(logging.DEBUG)

    if args.status:
        state = load_daemon_state()
        mem = get_memory_info()
        pid_exists = PID_FILE.exists()
        pid = PID_FILE.read_text().strip() if pid_exists else "N/A"
        alive = False
        if pid_exists:
            try:
                os.kill(int(pid), 0)
                alive = True
            except (ProcessLookupError, ValueError):
                pass

        print(json.dumps({
            "daemon_pid": pid,
            "daemon_alive": alive,
            "state": state,
            "memory": mem,
            "db_path": str(DB_PATH),
            "db_exists": DB_PATH.exists(),
            "max_message_id": get_max_message_id(),
        }, indent=2, default=str))
        return 0

    daemon = CosmoWatcherDaemon(
        interval=args.interval,
        dry_run=args.dry_run,
    )
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
