"""CSV and JSON export routes."""
import csv
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

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
from .cameras import _get_camera_profile
from .violations import _violation_evidence_media_type, _violation_evidence_url

logger = logging.getLogger(__name__)
router = APIRouter()

_RESEARCH_BUNDLE_SCHEMA_VERSION = "1.0"

_SAFETY_EVENT_COLUMNS = [
    "id", "timestamp", "camera_id", "violation_type", "object_id",
    "evidence_url", "evidence_media_type",
]
_CROSSING_COLUMNS = [
    "id", "timestamp", "camera_id", "line_id", "line_label", "direction",
    "class", "object_id", "frame_number", "source",
]
_SPEED_COLUMNS = ["id", "timestamp", "camera_id", "object_id", "speed_kmh", "source"]
_CONDITION_COLUMNS = [
    "id", "camera_id", "start", "end", "lighting", "weather", "notes",
]


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


def _get_speed_export_rows(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
):
    query = _apply_camera_filter(db.query(models.DBSpeed), models.DBSpeed, camera_id)
    query = _apply_time_filters(query, models.DBSpeed, start, end)
    rows = query.order_by(models.DBSpeed.timestamp.desc()).all()
    return [
        {
            "id": row.id,
            "timestamp": _serialize_dt(row.timestamp),
            "camera_id": row.camera_id,
            "object_id": row.object_id,
            "speed_kmh": row.speed_kmh,
            "source": row.source or "",
        }
        for row in rows
    ]


def _get_scene_condition_export_rows(db: Session, camera_id: str = None):
    query = db.query(models.DBSceneCondition)
    if camera_id:
        query = query.filter(models.DBSceneCondition.camera_id == camera_id)
    rows = query.order_by(models.DBSceneCondition.start).all()
    return [
        {
            "id": row.id,
            "camera_id": row.camera_id,
            "start": _serialize_dt(row.start),
            "end": _serialize_dt(row.end),
            "lighting": row.lighting or "",
            "weather": row.weather or "",
            "notes": row.notes or "",
        }
        for row in rows
    ]


def _read_platform_version() -> str:
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "unknown"


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


def _csv_bytes(fieldnames, rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


_BUNDLE_README = """Road User Intelligence Platform — Research Data Bundle

This archive is a reproducible export of event-level and aggregate traffic and
zebra-crossing safety data for a single camera and time window.

Contents:
  crossings.csv         Directional line-crossing events.
  speeds.csv            Per-object speed samples.
  safety_events.csv     Detected safety violations (evidence URLs, if enabled).
  scene_conditions.csv  Researcher-supplied lighting/weather window tags.
  traffic_flow.json     Aggregate summary, crossings, detections, violations,
                        and speed distribution for the same scope.
  manifest.json         Schema version, scope, calibration, column dictionaries,
                        and platform version for reproducibility.

Methodology & limitations:
  - Results depend heavily on camera placement and calibration
    (pixels-per-metre). The calibration used is recorded in manifest.json.
  - Object detection quality depends on scene conditions and model behaviour.
  - Safety-event logic is scene-sensitive and threshold-sensitive.
  - All data here is event-level or aggregate; no raw video is included.

See the repository README and docs/data_governance.md for responsible-use
expectations before publishing or redistributing derived data.
"""


def _build_research_bundle(
    db: Session, camera_id: str = None, start: datetime = None, end: datetime = None
) -> bytes:
    safety_rows = _get_safety_event_export_rows(db, camera_id, None, start, end)
    crossing_rows = _get_crossing_export_rows(db, camera_id, start, end)
    speed_rows = _get_speed_export_rows(db, camera_id, start, end)
    condition_rows = _get_scene_condition_export_rows(db, camera_id)
    traffic_flow = _get_traffic_flow_export_data(db, camera_id, start, end)

    calibration = None
    if camera_id:
        profile = _get_camera_profile(db, camera_id)
        if profile is not None:
            calibration = {
                "pixels_per_meter": profile.get("pixels_per_meter"),
                "speed_limit_kmh": profile.get("speed_limit_kmh"),
            }

    manifest = {
        "schema_version": _RESEARCH_BUNDLE_SCHEMA_VERSION,
        "platform_version": _read_platform_version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "camera_id": camera_id,
            "start": _serialize_dt(start),
            "end": _serialize_dt(end),
        },
        "calibration": calibration,
        "record_counts": {
            "crossings": len(crossing_rows),
            "speeds": len(speed_rows),
            "safety_events": len(safety_rows),
            "scene_conditions": len(condition_rows),
        },
        "columns": {
            "crossings.csv": _CROSSING_COLUMNS,
            "speeds.csv": _SPEED_COLUMNS,
            "safety_events.csv": _SAFETY_EVENT_COLUMNS,
            "scene_conditions.csv": _CONDITION_COLUMNS,
        },
    }

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("crossings.csv", _csv_bytes(_CROSSING_COLUMNS, crossing_rows))
        bundle.writestr("speeds.csv", _csv_bytes(_SPEED_COLUMNS, speed_rows))
        bundle.writestr("safety_events.csv", _csv_bytes(_SAFETY_EVENT_COLUMNS, safety_rows))
        bundle.writestr("scene_conditions.csv", _csv_bytes(_CONDITION_COLUMNS, condition_rows))
        bundle.writestr("traffic_flow.json", json.dumps(jsonable_encoder(traffic_flow), indent=2))
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
        bundle.writestr("README.txt", _BUNDLE_README)
    return archive.getvalue()


@router.get("/exports/research-bundle.zip")
def export_research_bundle(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = _build_research_bundle(db, camera_id, start, end)
    filename = _build_export_filename("research_bundle", "zip", camera_id, start, end)
    return StreamingResponse(
        iter([payload]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
