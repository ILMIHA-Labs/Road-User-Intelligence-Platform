"""CSV and JSON export routes."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ._shared import (
    _apply_camera_filter,
    _apply_supported_violation_filter,
    _apply_time_filters,
    _build_export_filename,
    _csv_download_response,
    _json_download_response,
    _serialize_dt,
)
from .analytics import (
    _get_analytics_summary_data,
    _get_crossing_analytics_data,
    _get_detection_analytics_data,
    _get_speed_distribution_data,
    _get_violation_breakdown_data,
)
from .violations import _violation_evidence_media_type, _violation_evidence_url

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_safety_event_export_rows(
    db: Session,
    camera_id: str = None,
    violation_type: str = None,
    start: datetime = None,
    end: datetime = None,
):
    query = _apply_supported_violation_filter(db.query(models.DBViolation))
    if camera_id:
        query = query.filter(models.DBViolation.camera_id == camera_id)
    if violation_type:
        query = query.filter(models.DBViolation.violation_type == violation_type)
    query = _apply_time_filters(query, models.DBViolation, start, end)
    rows = query.order_by(models.DBViolation.timestamp.desc()).all()
    return [
        {
            "id": row.id,
            "timestamp": _serialize_dt(row.timestamp),
            "camera_id": row.camera_id,
            "violation_type": row.violation_type,
            "object_id": row.object_id,
            "evidence_url": _violation_evidence_url(row) or "",
            "evidence_media_type": _violation_evidence_media_type(row) or "",
        }
        for row in rows
    ]


def _get_crossing_export_rows(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
):
    query = _apply_camera_filter(db.query(models.DBCrossing), models.DBCrossing, camera_id)
    query = _apply_time_filters(query, models.DBCrossing, start, end)
    rows = query.order_by(models.DBCrossing.timestamp.desc()).all()
    return [
        {
            "id": row.id,
            "timestamp": _serialize_dt(row.timestamp),
            "camera_id": row.camera_id,
            "line_id": row.line_id,
            "line_label": row.line_label,
            "direction": row.direction,
            "class": row.class_name,
            "object_id": row.object_id,
            "frame_number": row.frame_number if row.frame_number is not None else "",
            "source": row.source or "",
        }
        for row in rows
    ]


def _get_traffic_flow_export_data(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
):
    return {
        "generated_at": datetime.now(timezone.utc),
        "scope": {"camera_id": camera_id, "start": start, "end": end},
        "summary": _get_analytics_summary_data(db, camera_id, start, end),
        "crossings": _get_crossing_analytics_data(db, camera_id, start, end),
        "detections": _get_detection_analytics_data(db, camera_id, start, end),
        "violations": _get_violation_breakdown_data(db, camera_id, start, end),
        "speed_distribution": _get_speed_distribution_data(db, camera_id, start, end),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/exports/safety-events.csv")
def export_safety_events_csv(
    camera_id: str = Query(default=None),
    violation_type: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = _get_safety_event_export_rows(db, camera_id, violation_type, start, end)
    filename = _build_export_filename("safety_events", "csv", camera_id, start, end)
    return _csv_download_response(
        filename,
        ["id", "timestamp", "camera_id", "violation_type", "object_id", "evidence_url", "evidence_media_type"],
        rows,
    )


@router.get("/exports/crossings.csv")
def export_crossings_csv(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = _get_crossing_export_rows(db, camera_id, start, end)
    filename = _build_export_filename("crossings", "csv", camera_id, start, end)
    return _csv_download_response(
        filename,
        ["id", "timestamp", "camera_id", "line_id", "line_label", "direction", "class", "object_id", "frame_number", "source"],
        rows,
    )


@router.get("/exports/traffic-flow.json")
def export_traffic_flow_json(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = _get_traffic_flow_export_data(db, camera_id, start, end)
    filename = _build_export_filename("traffic_flow", "json", camera_id, start, end)
    return _json_download_response(filename, payload)
