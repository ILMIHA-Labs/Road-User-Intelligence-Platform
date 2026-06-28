"""Live camera status and dashboard SSE routes."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, StreamingResponse

from .. import models
from ..database import SessionLocal, get_db
from ._shared import _apply_supported_violation_filter, _serialize_dt
from .analytics import (
    _get_analytics_by_camera_data,
    _get_analytics_summary_data,
    _get_crossing_analytics_data,
    _get_detection_analytics_data,
    _get_recent_events_data,
    _get_speed_distribution_data,
    _get_violation_breakdown_data,
)
from .cameras import _get_camera_profile, _list_camera_profiles
from .violations import _live_snapshot_path

logger = logging.getLogger(__name__)
router = APIRouter()


def _camera_health_snapshot(camera_id: str, db: Session) -> dict:
    snapshot_path = _live_snapshot_path(camera_id)
    snapshot_available = snapshot_path.exists()
    snapshot_updated_at = None
    snapshot_age_seconds = None
    snapshot_fresh = False

    if snapshot_available:
        snapshot_updated = datetime.fromtimestamp(snapshot_path.stat().st_mtime, tz=timezone.utc)
        snapshot_updated_at = snapshot_updated.isoformat()
        snapshot_age_seconds = max(0, int((datetime.now(timezone.utc) - snapshot_updated).total_seconds()))
        snapshot_fresh = snapshot_age_seconds <= 10

    last_detection = db.query(func.max(models.DBDetection.timestamp)).filter(
        models.DBDetection.camera_id == camera_id
    ).scalar()
    last_speed = db.query(func.max(models.DBSpeed.timestamp)).filter(
        models.DBSpeed.camera_id == camera_id
    ).scalar()
    last_violation = _apply_supported_violation_filter(
        db.query(func.max(models.DBViolation.timestamp)).filter(models.DBViolation.camera_id == camera_id)
    ).scalar()
    last_crossing = db.query(func.max(models.DBCrossing.timestamp)).filter(
        models.DBCrossing.camera_id == camera_id
    ).scalar()

    recent_activity = [v for v in (last_detection, last_speed, last_violation, last_crossing) if v is not None]
    last_activity = max(recent_activity) if recent_activity else None
    last_activity_iso = _serialize_dt(last_activity)
    activity_age_seconds = None
    if last_activity is not None:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        activity_age_seconds = max(0, int((datetime.now(timezone.utc) - last_activity).total_seconds()))

    if snapshot_fresh or (activity_age_seconds is not None and activity_age_seconds <= 15):
        health = "online"
    elif snapshot_available or last_activity_iso:
        health = "idle"
    else:
        health = "offline"

    return {
        "camera_id": camera_id,
        "snapshot_available": snapshot_available,
        "snapshot_url": f"/live/cameras/{camera_id}/snapshot" if snapshot_available else None,
        "snapshot_updated_at": snapshot_updated_at,
        "snapshot_age_seconds": snapshot_age_seconds,
        "snapshot_fresh": snapshot_fresh,
        "last_detection_at": _serialize_dt(last_detection),
        "last_speed_at": _serialize_dt(last_speed),
        "last_violation_at": _serialize_dt(last_violation),
        "last_crossing_at": _serialize_dt(last_crossing),
        "last_activity_at": last_activity_iso,
        "activity_age_seconds": activity_age_seconds,
        "health": health,
    }


def _get_dashboard_snapshot_data(
    db: Session,
    camera_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    detail_camera_id: Optional[str] = None,
) -> dict:
    config_page = _list_camera_profiles(db, offset=0, limit=24)
    camera_profiles = list(config_page["cameras"])
    selected_ids = {v for v in (camera_id, detail_camera_id) if v}
    loaded_ids = {c.get("id") for c in camera_profiles}
    for selected_id in selected_ids - loaded_ids:
        profile = _get_camera_profile(db, selected_id)
        if profile:
            camera_profiles.append(profile)

    live_feeds = {
        "cameras": [
            _camera_health_snapshot(camera["id"], db)
            for camera in camera_profiles
            if camera.get("id")
        ],
        "total": config_page["total"],
        "limit": 24,
    }
    snapshot = {
        "summary": _get_analytics_summary_data(db, camera_id, start, end),
        "by_camera": _get_analytics_by_camera_data(db, start, end),
        "violations": _get_violation_breakdown_data(db, camera_id, start, end),
        "detections": _get_detection_analytics_data(db, camera_id, start, end),
        "crossings": _get_crossing_analytics_data(db, camera_id, start, end),
        "recent": _get_recent_events_data(db, camera_id, start, end, limit=20, offset=0),
        "speed_distribution": _get_speed_distribution_data(db, camera_id, start, end),
        "camera_configs": {
            "defaults": config_page["defaults"],
            "cameras": camera_profiles,
            "total": config_page["total"],
            "limit": 24,
            "bounded": True,
        },
        "live_feeds": live_feeds,
        "stream": {
            "status": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    if detail_camera_id:
        camera_stats = next(
            (item for item in snapshot["by_camera"]["cameras"] if item["camera_id"] == detail_camera_id),
            {"camera_id": detail_camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0},
        )
        snapshot["camera_detail"] = {
            "camera_id": detail_camera_id,
            "camera_stats": camera_stats,
            "recent": _get_recent_events_data(db, detail_camera_id, start, end, limit=20, offset=0),
            "violations": _get_violation_breakdown_data(db, detail_camera_id, start, end),
            "crossings": _get_crossing_analytics_data(db, detail_camera_id, start, end),
            "detections": _get_detection_analytics_data(db, detail_camera_id, start, end),
        }

    return snapshot


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/live/cameras")
def get_live_camera_statuses(
    q: str = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    config_page = _list_camera_profiles(db, q=q, offset=offset, limit=limit)
    statuses = [
        _camera_health_snapshot(camera["id"], db)
        for camera in config_page["cameras"]
        if camera.get("id")
    ]
    return {
        "cameras": statuses,
        "total": config_page["total"],
        "offset": offset,
        "limit": limit,
        "has_more": config_page["has_more"],
    }


@router.get("/live/cameras/{camera_id}")
def get_live_camera_status(camera_id: str, db: Session = Depends(get_db)):
    return _camera_health_snapshot(camera_id, db)


@router.get("/live/cameras/{camera_id}/snapshot")
def get_live_camera_snapshot(camera_id: str):
    snapshot_path = _live_snapshot_path(camera_id)
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail="No live snapshot available")
    return FileResponse(snapshot_path, media_type="image/jpeg")


@router.get("/live/dashboard")
async def stream_dashboard_state(
    request: Request,
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    detail_camera_id: str = Query(default=None),
    once: bool = Query(default=False),
):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            db = SessionLocal()
            try:
                payload = _get_dashboard_snapshot_data(
                    db,
                    camera_id=camera_id,
                    start=start,
                    end=end,
                    detail_camera_id=detail_camera_id,
                )
                encoded = json.dumps(jsonable_encoder(payload))
                yield f"event: snapshot\ndata: {encoded}\n\n"
            finally:
                db.close()
            if once:
                break
            await asyncio.sleep(2.0)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


