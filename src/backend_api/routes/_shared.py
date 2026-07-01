"""Shared utilities used by multiple route modules."""
import csv
import json
import logging
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional

from sqlalchemy import func
from starlette.responses import StreamingResponse

from .. import models
from ._config import _RETIRED_VIOLATION_TYPES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def _serialize_dt(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Query filters
# ---------------------------------------------------------------------------

def _apply_time_filters(query, model, start: datetime = None, end: datetime = None):
    if start is not None:
        query = query.filter(model.timestamp >= start)
    if end is not None:
        query = query.filter(model.timestamp <= end)
    return query


def _apply_camera_filter(query, model, camera_id: str = None):
    if camera_id:
        query = query.filter(model.camera_id == camera_id)
    return query


def _apply_supported_violation_filter(query):
    return query.filter(models.DBViolation.violation_type.notin_(_RETIRED_VIOLATION_TYPES))


def _daily_counts(db, model, camera_id: str = None, start: datetime = None, end: datetime = None) -> Dict[str, int]:
    """One grouped query: ISO date string -> count, for bucketing trend windows in Python."""
    query = _apply_time_filters(
        _apply_camera_filter(db.query(model), model, camera_id), model, start, end,
    )
    if model is models.DBViolation:
        query = _apply_supported_violation_filter(query)
    rows = (
        query.with_entities(func.date(model.timestamp).label("day"), func.count(model.id).label("count"))
        .group_by("day")
        .all()
    )
    return {row.day: row.count for row in rows}


# ---------------------------------------------------------------------------
# Row serializers
# ---------------------------------------------------------------------------

def _serialize_detection_class_rows(rows) -> List[dict]:
    items = [{"class": row.class_name, "count": row.count} for row in rows]
    return sorted(items, key=lambda item: (-item["count"], item["class"]))


def _serialize_recent_detections(rows) -> List[dict]:
    return [
        {
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "object_id": row.object_id,
            "class": row.class_name,
            "helmet_status": row.helmet_status,
            "bbox": row.bbox,
            "confidence": row.confidence,
            "frame_number": row.frame_number,
            "source": row.source,
        }
        for row in rows
    ]


def _serialize_recent_speeds(rows) -> List[dict]:
    return [
        {
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "object_id": row.object_id,
            "speed_kmh": row.speed_kmh,
            "source": row.source,
        }
        for row in rows
    ]


def _serialize_recent_violations(rows) -> List[dict]:
    from .violations import _violation_evidence_url, _violation_evidence_media_type
    return [
        {
            "id": row.id,
            "violation_type": row.violation_type,
            "object_id": row.object_id,
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "evidence_url": _violation_evidence_url(row),
            "evidence_media_type": _violation_evidence_media_type(row),
            "review_status": row.review_status or "needs_review",
            "review_notes": row.review_notes,
            "reviewed_at": row.reviewed_at,
        }
        for row in rows
    ]


def _serialize_recent_crossings(rows) -> List[dict]:
    return [
        {
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "object_id": row.object_id,
            "class": row.class_name,
            "direction": row.direction,
            "line_id": row.line_id,
            "line_label": row.line_label,
            "frame_number": row.frame_number,
            "source": row.source,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _build_export_filename(
    prefix: str,
    extension: str,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
) -> str:
    parts = [prefix]
    if camera_id:
        parts.append(camera_id)
    if start:
        parts.append(start.strftime("%Y%m%d"))
    if end:
        parts.append(end.strftime("%Y%m%d"))
    return "_".join(parts) + f".{extension}"


def _csv_download_response(filename: str, fieldnames: List[str], rows: List[dict]):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _json_download_response(filename: str, payload: dict):
    from fastapi.encoders import jsonable_encoder
    content = json.dumps(jsonable_encoder(payload), indent=2)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
