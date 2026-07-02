"""
ha_context.py — Módulo PREMIUM opcional para integración con Home Assistant.
Proporciona datos biométricos (ritmo cardíaco, pasos, actividad, GPS) 
que enriquecen el Emotional Awareness Engine.

Este módulo es OPCIONAL. Si no hay HA configurado, el engine core 
funciona perfectamente solo con análisis de texto.

Uso:
    from ha_context import get_biometric_context, is_available
    
    if is_available():
        ctx = get_biometric_context()
        # ctx = {"heart_rate": 72, "steps": 3500, "activity": "passive", ...}
"""

import os
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path

log = logging.getLogger("emotional-engine.ha")

# HA config — loaded from environment or config file
HA_URL = os.environ.get("HA_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Entity IDs for health monitoring
ENTITIES = {
    "heart_rate": "sensor.galaxy_watch4_r8vj_heart_rate",
    "steps": "sensor.galaxy_watch4_r8vj_daily_steps",
    "calories": "sensor.galaxy_watch4_r8vj_daily_calories",
    "activity": "sensor.galaxy_watch4_r8vj_activity_state",
    "gps": "device_tracker.xiaomi",
}


def is_available() -> bool:
    """Verifica si HA está configurado y accesible."""
    if not HA_TOKEN:
        # Try loading from proxmox.env as fallback
        env_file = Path.home() / ".hermes" / "proxmox.env"
        if env_file.exists():
            return True  # Token available, will be loaded on first call
        return False
    
    try:
        req = urllib.request.Request(
            f"{HA_URL}/api/",
            headers={"Authorization": f"Bearer {HA_TOKEN}"}
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


def _ha_api_call(entity_id: str) -> dict | None:
    """Llama a la API de Home Assistant para obtener el estado de una entidad."""
    token = HA_TOKEN
    if not token:
        env_file = Path.home() / ".hermes" / "proxmox.env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("HA_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    
    if not token:
        return None
    
    try:
        req = urllib.request.Request(
            f"{HA_URL}/api/states/{entity_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.debug(f"HA API error for {entity_id}: {e}")
        return None


def get_biometric_context() -> dict:
    """
    Obtiene el contexto biométrico completo del usuario.
    Retorna un dict con los datos disponibles, o vacío si HA no está disponible.
    
    Returns:
        {
            "available": True/False,
            "heart_rate": {"value": 72, "unit": "bpm", "timestamp": "..."},
            "steps": {"value": 3500, "unit": "steps", "timestamp": "..."},
            "activity": "passive",
            "gps": {"latitude": -12.xxx, "longitude": -76.xxx, "state": "home"},
            "alerts": []  # Health alerts (e.g., high heart rate)
        }
    """
    if not is_available():
        return {"available": False}
    
    context = {"available": True, "alerts": []}
    
    # Heart rate
    hr_data = _ha_api_call(ENTITIES["heart_rate"])
    if hr_data:
        hr_value = float(hr_data.get("state", 0))
        context["heart_rate"] = {
            "value": hr_value,
            "unit": hr_data.get("attributes", {}).get("unit_of_measurement", "bpm"),
            "timestamp": hr_data.get("last_updated", "")
        }
        # Alert: elevated heart rate at rest (>100 bpm)
        activity = _ha_api_call(ENTITIES["activity"])
        is_resting = activity and activity.get("state") == "passive"
        if is_resting and hr_value > 100:
            context["alerts"].append({
                "type": "high_heart_rate",
                "message": f"Ritmo cardíaco elevado en reposo: {hr_value} bpm",
                "severity": "medium"
            })
        if is_resting and hr_value > 120:
            context["alerts"][-1]["severity"] = "high"
    
    # Steps
    steps_data = _ha_api_call(ENTITIES["steps"])
    if steps_data:
        context["steps"] = {
            "value": float(steps_data.get("state", 0)),
            "unit": "steps",
            "timestamp": steps_data.get("last_updated", "")
        }
    
    # Activity state
    activity_data = _ha_api_call(ENTITIES["activity"])
    if activity_data:
        context["activity"] = activity_data.get("state", "unknown")
    
    # GPS location
    gps_data = _ha_api_call(ENTITIES["gps"])
    if gps_data:
        attrs = gps_data.get("attributes", {})
        context["gps"] = {
            "state": gps_data.get("state", "unknown"),
            "latitude": attrs.get("latitude"),
            "longitude": attrs.get("longitude"),
            "timestamp": gps_data.get("last_updated", "")
        }
    
    return context


def get_health_summary() -> str:
    """Genera un resumen de salud en texto para incluir en el contexto del check-in."""
    ctx = get_biometric_context()
    if not ctx.get("available"):
        return ""
    
    parts = []
    if "heart_rate" in ctx:
        parts.append(f"❤️ Ritmo: {ctx['heart_rate']['value']} bpm")
    if "steps" in ctx:
        parts.append(f"👣 Pasos: {int(ctx['steps']['value'])}")
    if "activity" in ctx:
        parts.append(f"🏃 Estado: {ctx['activity']}")
    if "gps" in ctx:
        parts.append(f"📍 {ctx['gps']['state']}")
    
    if ctx.get("alerts"):
        alert_msgs = [a["message"] for a in ctx["alerts"]]
        parts.append(f"⚠️ Alertas: {'; '.join(alert_msgs)}")
    
    return " | ".join(parts)


# Self-test
if __name__ == "__main__":
    print(f"HA disponible: {is_available()}")
    if is_available():
        ctx = get_biometric_context()
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str))
        print(f"\nResumen: {get_health_summary()}")
