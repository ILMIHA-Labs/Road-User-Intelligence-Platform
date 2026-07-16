"""Alert history and configuration routes."""
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ._shared import _serialize_dt

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_alert(row: models.DBAlert) -> dict:
    return {
        "id": row.id,
        "created_at": _serialize_dt(row.created_at),
        "alert_type": row.alert_type,
        "camera_id": row.camera_id,
        "severity": row.severity,
        "payload": row.payload,
        "delivered": row.delivered,
        "delivery_error": row.delivery_error,
    }


def _redact_webhook(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    host = parts.hostname or "configured"
    return f"{parts.scheme}://{host}" if parts.scheme else host


@router.get("/alerts")
def list_alerts(
    alert_type: str = Query(default=None),
    camera_id: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(models.DBAlert)
    if alert_type:
        query = query.filter(models.DBAlert.alert_type == alert_type)
    if camera_id:
        query = query.filter(models.DBAlert.camera_id == camera_id)
    total = query.count()
    rows = (
        query.order_by(models.DBAlert.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "alerts": [_serialize_alert(row) for row in rows],
    }


@router.get("/alerts/config")
def get_alerts_config():
    from ._config import (
        _ALERT_CAMERA_RECOVERY_ENABLED,
        _ALERT_DEBOUNCE_SECONDS,
        _ALERT_MQTT_ENABLED,
        _ALERT_MQTT_TOPIC,
        _ALERT_VIOLATION_TYPES,
        _ALERT_WEBHOOK_URL,
        _ALERTS_ENABLED,
        _CAMERA_HEALTH_POLL_SECONDS,
        _CAMERA_OFFLINE_AFTER_SECONDS,
    )
    return {
        "alerts_enabled": _ALERTS_ENABLED,
        "webhook_configured": bool(_ALERT_WEBHOOK_URL),
        "webhook_target": _redact_webhook(_ALERT_WEBHOOK_URL),
        "mqtt_enabled": _ALERT_MQTT_ENABLED,
        "mqtt_topic": _ALERT_MQTT_TOPIC if _ALERT_MQTT_ENABLED else None,
        "violation_types": sorted(_ALERT_VIOLATION_TYPES) or "all",
        "debounce_seconds": _ALERT_DEBOUNCE_SECONDS,
        "camera_offline_after_seconds": _CAMERA_OFFLINE_AFTER_SECONDS,
        "camera_health_poll_seconds": _CAMERA_HEALTH_POLL_SECONDS,
        "camera_recovery_alerts": _ALERT_CAMERA_RECOVERY_ENABLED,
    }


@router.post("/alerts/test", status_code=201)
def send_test_alert(db: Session = Depends(get_db)):
    """Fire a synthetic alert through the configured channels to verify setup."""
    from ..alerting import Alert, record_and_dispatch
    alert = Alert(
        alert_type="test",
        camera_id=None,
        severity="info",
        dedup_key=None,
        payload={"alert_type": "test", "message": "Road User Intelligence Platform test alert"},
    )
    created = record_and_dispatch(db, [alert])
    return {"created": created}
