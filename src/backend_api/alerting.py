"""Operational alerting: safety-event and camera-health notifications.

Config-gated (``ALERTS_ENABLED``, default off) and privacy-aware — alert
payloads carry event-level metadata only (camera id, type, timestamp, counts),
never imagery or PII. Every alert is recorded to the ``alerts`` table whether or
not external delivery succeeds, so the history is auditable via ``/alerts``.

Delivery (webhook, optional MQTT publish) runs on a background executor so it
never blocks event ingest, and is fully wrapped in try/except so a failing
channel can never break a request or the health-poll loop.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import models
from .database import SessionLocal

logger = logging.getLogger(__name__)

# Set True in tests to run delivery inline instead of on the executor.
SYNCHRONOUS_DELIVERY = False

_DELIVERY_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_dedup_lock = threading.Lock()
_last_sent: Dict[str, float] = {}


@dataclass
class Alert:
    alert_type: str
    camera_id: Optional[str]
    severity: str = "info"
    dedup_key: Optional[str] = None
    payload: dict = field(default_factory=dict)


def _cfg():
    """Late import so config is read at call time (avoids import cycles and
    lets tests monkeypatch ``backend_api.routes._config`` values)."""
    from .routes import _config
    return _config


# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------

def _should_send(dedup_key: Optional[str], now: float, debounce_seconds: float) -> bool:
    if not dedup_key:
        return True
    with _dedup_lock:
        last = _last_sent.get(dedup_key)
        if last is not None and (now - last) < debounce_seconds:
            return False
        _last_sent[dedup_key] = now
        return True


def reset_debounce() -> None:
    """Clear debounce state (used by tests)."""
    with _dedup_lock:
        _last_sent.clear()


# ---------------------------------------------------------------------------
# Delivery channels (best-effort)
# ---------------------------------------------------------------------------

def _send_webhook(url: str, payload: dict, timeout: float) -> None:
    import httpx
    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()


def _send_mqtt(host: str, port: int, topic: str, payload: dict) -> None:
    import json

    import paho.mqtt.client as mqtt
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(host, port, keepalive=10)
    client.loop_start()
    try:
        info = client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=5.0)
    finally:
        client.loop_stop()
        client.disconnect()


def _deliver(alert_id: int) -> None:
    cfg = _cfg()
    db = SessionLocal()
    try:
        row = db.query(models.DBAlert).filter(models.DBAlert.id == alert_id).first()
        if row is None:
            return
        payload = dict(row.payload or {})
        errors: List[str] = []
        delivered = False
        attempted = False

        if cfg._ALERT_WEBHOOK_URL:
            attempted = True
            try:
                _send_webhook(cfg._ALERT_WEBHOOK_URL, payload, cfg._ALERT_WEBHOOK_TIMEOUT_SECONDS)
                delivered = True
            except Exception as exc:  # best-effort: never propagate
                errors.append(f"webhook: {exc}")
                logger.warning("Alert %s webhook delivery failed: %s", alert_id, exc)

        if cfg._ALERT_MQTT_ENABLED:
            attempted = True
            try:
                _send_mqtt(
                    cfg._ALERT_MQTT_BROKER_HOST, cfg._ALERT_MQTT_BROKER_PORT,
                    cfg._ALERT_MQTT_TOPIC, payload,
                )
                delivered = True
            except Exception as exc:
                errors.append(f"mqtt: {exc}")
                logger.warning("Alert %s MQTT delivery failed: %s", alert_id, exc)

        if not attempted:
            errors.append("no delivery channels configured")

        row.delivered = delivered
        row.delivery_error = "; ".join(errors) if errors else None
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Alert %s delivery bookkeeping failed: %s", alert_id, exc)
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def record_and_dispatch(db, alerts: List[Alert]) -> List[int]:
    """Persist alert rows (respecting debounce), then deliver in the background.

    Returns the ids of the alert rows that were created (i.e. not debounced).
    """
    cfg = _cfg()
    now = time.monotonic()
    pending = []
    for alert in alerts:
        if not _should_send(alert.dedup_key, now, cfg._ALERT_DEBOUNCE_SECONDS):
            continue
        row = models.DBAlert(
            alert_type=alert.alert_type,
            camera_id=alert.camera_id,
            severity=alert.severity,
            dedup_key=alert.dedup_key,
            payload=alert.payload,
            delivered=False,
        )
        db.add(row)
        pending.append(row)
    if not pending:
        return []
    db.commit()

    created: List[int] = []
    for row in pending:
        db.refresh(row)
        alert_id = row.id
        if alert_id is None:
            continue
        created.append(alert_id)
        if SYNCHRONOUS_DELIVERY:
            _deliver(alert_id)
        else:
            _DELIVERY_EXECUTOR.submit(_deliver, alert_id)
    return created


# ---------------------------------------------------------------------------
# Violation alerts
# ---------------------------------------------------------------------------

def build_violation_alert(violation: models.DBViolation) -> Alert:
    return Alert(
        alert_type="violation",
        camera_id=violation.camera_id,
        severity="warning",
        dedup_key=f"violation:{violation.camera_id}:{violation.violation_type}",
        payload={
            "alert_type": "violation",
            "camera_id": violation.camera_id,
            "violation_type": violation.violation_type,
            "object_id": violation.object_id,
            "timestamp": violation.timestamp.isoformat() if violation.timestamp else None,
            "severity": "warning",
        },
    )


def dispatch_violation_alerts(db, violations: List[models.DBViolation]) -> List[int]:
    cfg = _cfg()
    if not cfg._ALERTS_ENABLED:
        return []
    allowed = cfg._ALERT_VIOLATION_TYPES
    selected = [
        v for v in violations
        if not allowed or v.violation_type in allowed
    ]
    if not selected:
        return []
    return record_and_dispatch(db, [build_violation_alert(v) for v in selected])


# ---------------------------------------------------------------------------
# Camera health
# ---------------------------------------------------------------------------

def evaluate_camera_health(
    previous_state: Optional[str],
    snapshot: dict,
    offline_after_seconds: float,
    recovery_enabled: bool = True,
) -> Tuple[Optional[Alert], str]:
    """Pure transition function: (previous state, current snapshot) -> (alert?, new state).

    States are "online", "offline", or "unknown". No alert is emitted on the
    first meaningful observation (avoids startup noise); an offline alert fires
    once on online->offline, and a recovery alert (if enabled) on offline->online.
    """
    camera_id = snapshot.get("camera_id")
    age = snapshot.get("activity_age_seconds")
    if age is None:
        current = "unknown"
    elif age > offline_after_seconds:
        current = "offline"
    else:
        current = "online"

    if previous_state in (None, "unknown"):
        return None, current

    if previous_state == "online" and current == "offline":
        alert = Alert(
            alert_type="camera_offline",
            camera_id=camera_id,
            severity="warning",
            dedup_key=f"camera_offline:{camera_id}",
            payload={
                "alert_type": "camera_offline",
                "camera_id": camera_id,
                "activity_age_seconds": age,
                "last_activity_at": snapshot.get("last_activity_at"),
                "severity": "warning",
            },
        )
        return alert, "offline"

    if previous_state == "offline" and current == "online":
        if not recovery_enabled:
            return None, "online"
        alert = Alert(
            alert_type="camera_recovered",
            camera_id=camera_id,
            severity="info",
            dedup_key=f"camera_recovered:{camera_id}",
            payload={
                "alert_type": "camera_recovered",
                "camera_id": camera_id,
                "activity_age_seconds": age,
                "last_activity_at": snapshot.get("last_activity_at"),
                "severity": "info",
            },
        )
        return alert, "online"

    # No transition. A transient "unknown" (no activity this pass) keeps the
    # last known state; previous_state is a real state here (guarded above).
    assert previous_state is not None
    return None, previous_state if current == "unknown" else current


class CameraHealthMonitor:
    """Background thread that polls camera health and dispatches transition alerts."""

    def __init__(self) -> None:
        self._states: Dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        cfg = _cfg()
        if not cfg._ALERTS_ENABLED:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera-health-monitor", daemon=True)
        self._thread.start()
        logger.info("Camera health monitor started.")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None

    def _run(self) -> None:
        cfg = _cfg()
        poll_seconds = max(1.0, cfg._CAMERA_HEALTH_POLL_SECONDS)
        while not self._stop.wait(poll_seconds):
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Camera health poll failed: %s", exc)

    def run_once(self) -> List[int]:
        """One poll pass. Returns ids of any alerts dispatched (used by tests)."""
        cfg = _cfg()
        from .routes.cameras import _list_camera_profiles
        from .routes.live import _camera_health_snapshot

        created: List[int] = []
        db = SessionLocal()
        try:
            profiles = _list_camera_profiles(db, offset=0, limit=1000)["cameras"]
            alerts: List[Alert] = []
            for camera in profiles:
                camera_id = camera.get("id")
                if not camera_id:
                    continue
                snapshot = _camera_health_snapshot(camera_id, db)
                alert, new_state = evaluate_camera_health(
                    self._states.get(camera_id),
                    snapshot,
                    cfg._CAMERA_OFFLINE_AFTER_SECONDS,
                    cfg._ALERT_CAMERA_RECOVERY_ENABLED,
                )
                self._states[camera_id] = new_state
                if alert is not None:
                    alerts.append(alert)
            if alerts:
                created = record_and_dispatch(db, alerts)
        finally:
            db.close()
        return created


camera_monitor = CameraHealthMonitor()
