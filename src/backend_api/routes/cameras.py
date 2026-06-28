"""Camera registry, profile, and setup routes."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import cv2
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from .. import models
from ..database import get_db
from common.camera_config import normalize_counting_line_definitions, normalize_zone_definitions
from ._config import (
    _CAMERA_DEFAULTS_CACHE,
    _CAMERAS_CONFIG_PATH,
    _RETIRED_CAMERA_CONFIG_FIELDS,
    _SETUP_PREVIEW_DIR,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SetupPreviewRequest(BaseModel):
    source: str
    camera_id: Optional[str] = None


class SetupCountingLineInput(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    points: List[List[float]]


class SetupZebraZoneInput(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    points: List[List[float]]


class CameraSetupSaveRequest(BaseModel):
    camera_id: str
    source: str
    location: Optional[str] = ""
    target_fps: Optional[int] = None
    pixels_per_meter: Optional[float] = None
    speed_limit_kmh: Optional[float] = None
    live_feed_type: Optional[str] = None
    live_feed_url: Optional[str] = None
    preview_image_url: Optional[str] = None
    preview_frame_width: Optional[int] = None
    preview_frame_height: Optional[int] = None
    counting_lines: List[SetupCountingLineInput] = Field(default_factory=list)
    zebra_zones: List[SetupZebraZoneInput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _sanitize_camera_id(camera_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in camera_id.strip())
    return safe or "camera_setup"


def _setup_preview_path(camera_id: str) -> Path:
    return _SETUP_PREVIEW_DIR / camera_id / "frame.jpg"


def _resolve_source_path(source: str) -> Path:
    source_path = Path(source)
    if source_path.is_absolute():
        return source_path
    return (_CAMERAS_CONFIG_PATH.parent.parent / source).resolve()


def _extract_preview_frame(source: str):
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    resolved_source = _resolve_source_path(source)

    if resolved_source.exists() and resolved_source.suffix.lower() in image_extensions:
        frame = cv2.imread(str(resolved_source))
    else:
        capture_source = str(resolved_source) if resolved_source.exists() else source
        capture = cv2.VideoCapture(capture_source)
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            frame = None

    if frame is None:
        raise HTTPException(status_code=400, detail="Unable to read preview frame from source")
    return frame, str(resolved_source if resolved_source.exists() else source)


def _read_raw_camera_config():
    try:
        with open(_CAMERAS_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _write_raw_camera_config(raw_config: dict):
    _CAMERAS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CAMERAS_CONFIG_PATH, "w") as f:
        yaml.safe_dump(raw_config, f, sort_keys=False)


def _get_camera_defaults() -> dict:
    try:
        mtime_ns = _CAMERAS_CONFIG_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = None
    path_key = str(_CAMERAS_CONFIG_PATH)
    if (
        _CAMERA_DEFAULTS_CACHE["path"] == path_key
        and _CAMERA_DEFAULTS_CACHE["mtime_ns"] == mtime_ns
    ):
        return dict(_CAMERA_DEFAULTS_CACHE["defaults"])
    defaults = _read_raw_camera_config().get("defaults", {})
    _CAMERA_DEFAULTS_CACHE.update({"path": path_key, "mtime_ns": mtime_ns, "defaults": dict(defaults)})
    return dict(defaults)


def _without_retired_camera_fields(payload: dict) -> dict:
    visible = dict(payload or {})
    for key in _RETIRED_CAMERA_CONFIG_FIELDS:
        visible.pop(key, None)
    return visible


def _effective_camera_profile(defaults: dict, camera_payload: dict) -> dict:
    profile = {**defaults, **(camera_payload or {})}
    profile = _without_retired_camera_fields(profile)
    profile["zones"] = normalize_zone_definitions(profile.get("zones"))
    profile["counting_lines"] = normalize_counting_line_definitions(profile.get("counting_lines"))
    return profile


def _upsert_camera_profile(db: Session, camera_payload: dict, source: str):
    camera_id = str(camera_payload.get("id", "")).strip()
    if not camera_id:
        raise HTTPException(status_code=400, detail="Camera profile must include an id")
    normalized = dict(camera_payload)
    normalized["id"] = camera_id
    normalized["zones"] = normalize_zone_definitions(normalized.get("zones"))
    normalized["counting_lines"] = normalize_counting_line_definitions(normalized.get("counting_lines"))
    row = db.query(models.DBCameraConfig).filter(models.DBCameraConfig.camera_id == camera_id).first()
    if row is None:
        row = models.DBCameraConfig(
            camera_id=camera_id,
            location=normalized.get("location"),
            enabled=bool(normalized.get("enabled", True)),
            profile=normalized,
            source=source,
            version=1,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.location = normalized.get("location")
        row.enabled = bool(normalized.get("enabled", True))
        row.profile = normalized
        row.source = source
        row.version = int(row.version or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
    return row


def _seed_camera_registry(db: Session):
    raw = _read_raw_camera_config()
    for camera in raw.get("cameras", []):
        camera_id = str(camera.get("id", "")).strip()
        if not camera_id:
            continue
        _upsert_camera_profile(db, camera, source="yaml_runtime")
    db.commit()


def _camera_profile_query(db: Session, q: Optional[str] = None):
    query = db.query(models.DBCameraConfig)
    if q:
        term = f"{q.strip()}%"
        query = query.filter(
            or_(
                models.DBCameraConfig.camera_id.ilike(term),
                models.DBCameraConfig.location.ilike(term),
            )
        )
    return query


def _list_camera_profiles(db: Session, q: Optional[str] = None, offset: int = 0, limit: int = 50):
    defaults = _get_camera_defaults()
    query = _camera_profile_query(db, q)
    total = query.count()
    rows = query.order_by(models.DBCameraConfig.camera_id.asc()).offset(offset).limit(limit).all()
    return {
        "defaults": _without_retired_camera_fields(defaults),
        "cameras": [_effective_camera_profile(defaults, row.profile) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(rows) < total,
    }


def _get_camera_profile(db: Session, camera_id: str):
    defaults = _get_camera_defaults()
    row = db.query(models.DBCameraConfig).filter(models.DBCameraConfig.camera_id == camera_id).first()
    return _effective_camera_profile(defaults, row.profile) if row is not None else None


def _normalize_setup_counting_lines(lines: List[SetupCountingLineInput]):
    payload = []
    for index, line in enumerate(lines or [], start=1):
        payload.append({
            "id": line.id or f"count_line_{index}",
            "label": line.label or f"Count Line {index}",
            "points": line.points,
            "enabled": True,
        })
    return normalize_counting_line_definitions(payload)


def _normalize_setup_zebra_zones(zones: List[SetupZebraZoneInput]):
    payload = []
    for index, zone in enumerate(zones or [], start=1):
        payload.append({
            "id": zone.id or f"zebra_crossing_{index}",
            "label": zone.label or f"Zebra Crossing {index}",
            "type": "polygon",
            "category": "zebra_crossing",
            "points": zone.points,
        })
    return normalize_zone_definitions(payload)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/cameras/config")
def get_cameras_config(
    q: str = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return _list_camera_profiles(db, q=q, offset=offset, limit=limit)


@router.get("/cameras/config/{camera_id}")
def get_camera_config(camera_id: str, db: Session = Depends(get_db)):
    profile = _get_camera_profile(db, camera_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Camera configuration not found")
    return profile


@router.post("/setup/preview-frame")
def create_setup_preview(request: SetupPreviewRequest):
    camera_id = _sanitize_camera_id(request.camera_id or Path(request.source).stem or "camera_setup")
    frame, resolved_source = _extract_preview_frame(request.source)
    preview_path = _setup_preview_path(camera_id)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(preview_path), frame):
        raise HTTPException(status_code=500, detail="Failed to write preview frame")
    height, width = frame.shape[:2]
    return {
        "camera_id": camera_id,
        "source": request.source,
        "resolved_source": resolved_source,
        "preview_url": f"/setup/previews/{camera_id}/frame",
        "width": int(width),
        "height": int(height),
    }


@router.get("/setup/previews/{camera_id}/frame")
def get_setup_preview(camera_id: str):
    preview_path = _setup_preview_path(camera_id)
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="No setup preview available")
    return FileResponse(preview_path, media_type="image/jpeg")


@router.post("/setup/camera-config")
def save_camera_setup(request: CameraSetupSaveRequest, db: Session = Depends(get_db)):
    preview_camera_id = _sanitize_camera_id(request.camera_id)
    raw = _read_raw_camera_config()
    defaults = raw.get("defaults", {})
    yaml_cameras = raw.get("cameras", [])

    normalized_lines = _normalize_setup_counting_lines(request.counting_lines)
    normalized_zebra_zones = _normalize_setup_zebra_zones(request.zebra_zones)

    existing_row = db.query(models.DBCameraConfig).filter(
        models.DBCameraConfig.camera_id == request.camera_id
    ).first()
    existing_camera = dict(existing_row.profile) if existing_row is not None else {}
    existing_zones = normalize_zone_definitions(existing_camera.get("zones"))
    retained_non_zebra_zones = [zone for zone in existing_zones if zone.get("category") != "zebra_crossing"]

    camera_payload = {
        **existing_camera,
        "id": request.camera_id,
        "url": request.source,
        "location": request.location or existing_camera.get("location") or "",
        "target_fps": request.target_fps if request.target_fps is not None else existing_camera.get("target_fps", 15),
        "pixels_per_meter": request.pixels_per_meter if request.pixels_per_meter is not None else existing_camera.get("pixels_per_meter", defaults.get("pixels_per_meter", 25.0)),
        "speed_limit_kmh": request.speed_limit_kmh if request.speed_limit_kmh is not None else existing_camera.get("speed_limit_kmh", defaults.get("speed_limit_kmh", 60.0)),
        "live_feed_type": request.live_feed_type if request.live_feed_type is not None else existing_camera.get("live_feed_type", "preview"),
        "live_feed_url": request.live_feed_url if request.live_feed_url is not None else existing_camera.get("live_feed_url"),
        "preview_image_url": request.preview_image_url if request.preview_image_url is not None else existing_camera.get("preview_image_url", f"/setup/previews/{preview_camera_id}/frame"),
        "preview_frame_width": request.preview_frame_width if request.preview_frame_width is not None else existing_camera.get("preview_frame_width"),
        "preview_frame_height": request.preview_frame_height if request.preview_frame_height is not None else existing_camera.get("preview_frame_height"),
        "counting_lines": normalized_lines,
        "zones": retained_non_zebra_zones + normalized_zebra_zones,
    }

    row = _upsert_camera_profile(db, camera_payload, source="dashboard_setup")
    db.commit()

    yaml_index = next(
        (i for i, cam in enumerate(yaml_cameras) if cam.get("id") == request.camera_id), None
    )
    if yaml_index is None:
        yaml_cameras.append(camera_payload)
    else:
        yaml_cameras[yaml_index] = camera_payload
    raw["cameras"] = yaml_cameras
    _write_raw_camera_config(raw)

    return {"message": "Camera setup saved", "camera": _effective_camera_profile(defaults, row.profile)}
