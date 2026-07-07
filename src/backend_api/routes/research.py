"""Research-oriented traffic analytics and scene-condition tagging routes.

These endpoints turn the raw event tables (crossings, speeds, detections)
into the aggregate measures road-safety researchers publish: hourly/peak-hour
demand profiles, vehicle headway distributions, and speed-limit compliance.
Scene-condition tags let those measures be sliced by lighting/weather without
inferring conditions from imagery.
"""
import logging
from datetime import datetime
from statistics import mean, median
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ._shared import _apply_camera_filter, _apply_time_filters, _serialize_dt
from .cameras import _get_camera_profile

logger = logging.getLogger(__name__)
router = APIRouter()

VEHICLE_CLASSES = frozenset({"car", "bus", "truck", "motorcycle"})
LIGHTING_VALUES = frozenset({"day", "dusk", "night"})
WEATHER_VALUES = frozenset({"clear", "rain", "fog", "snow"})

# Headway distribution buckets (upper bounds, seconds); last bucket is open.
_HEADWAY_BUCKETS: Tuple[float, ...] = (1.0, 2.0, 3.0, 5.0, 10.0)
_CRITICAL_HEADWAY_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Scene-condition helpers
# ---------------------------------------------------------------------------

def _matching_condition_windows(
    db: Session, camera_id: Optional[str], lighting: Optional[str], weather: Optional[str]
) -> Optional[List[Tuple[datetime, datetime]]]:
    """Return [start, end) windows matching the requested tags.

    ``None`` means "no scene filter requested" (caller should not restrict).
    An empty list means "filter requested but nothing matches" (caller should
    return an empty result set).
    """
    if not lighting and not weather:
        return None
    query = db.query(models.DBSceneCondition)
    if camera_id:
        query = query.filter(models.DBSceneCondition.camera_id == camera_id)
    if lighting:
        query = query.filter(models.DBSceneCondition.lighting == lighting)
    if weather:
        query = query.filter(models.DBSceneCondition.weather == weather)
    windows: List[Tuple[datetime, datetime]] = []
    for row in query.all():
        if row.start is not None and row.end is not None:
            windows.append((row.start, row.end))
    return windows


def _apply_scene_windows(query, model, windows: List[Tuple[datetime, datetime]]):
    if not windows:
        # Filter requested but no matching windows: match nothing.
        return query.filter(model.timestamp < model.timestamp)
    clauses = [
        (model.timestamp >= start) & (model.timestamp < end)
        for start, end in windows
    ]
    return query.filter(or_(*clauses))


def _scoped_query(db, model, camera_id, start, end, windows):
    query = _apply_time_filters(_apply_camera_filter(db.query(model), model, camera_id), model, start, end)
    if windows is not None:
        query = _apply_scene_windows(query, model, windows)
    return query


# ---------------------------------------------------------------------------
# Traffic profile
# ---------------------------------------------------------------------------

def _get_traffic_profile_data(db, camera_id, start, end, windows) -> dict:
    rows = _scoped_query(db, models.DBCrossing, camera_id, start, end, windows).all()
    hourly = [0] * 24
    weekday = 0
    weekend = 0
    for row in rows:
        ts = row.timestamp
        if ts is None:
            continue
        hourly[ts.hour] += 1
        if ts.weekday() >= 5:
            weekend += 1
        else:
            weekday += 1
    total = len(rows)
    peak_count = max(hourly) if total else 0
    peak_hour = hourly.index(peak_count) if total else None
    # Peak-hour factor: peak-hour volume vs. average hourly volume over
    # hours that saw any activity.
    active_hours = sum(1 for count in hourly if count > 0)
    avg_active = (total / active_hours) if active_hours else 0.0
    peak_hour_factor = round(peak_count / avg_active, 3) if avg_active else None
    return {
        "camera_id": camera_id,
        "total_crossings": total,
        "hourly_counts": hourly,
        "peak_hour": peak_hour,
        "peak_hour_count": peak_count,
        "peak_hour_factor": peak_hour_factor,
        "weekday_count": weekday,
        "weekend_count": weekend,
    }


# ---------------------------------------------------------------------------
# Headways
# ---------------------------------------------------------------------------

def _get_headways_data(db, camera_id, start, end, windows) -> dict:
    rows = _scoped_query(db, models.DBCrossing, camera_id, start, end, windows).all()
    # Group vehicle crossing timestamps per (line_id, direction).
    groups: dict = {}
    for row in rows:
        if row.class_name not in VEHICLE_CLASSES or row.timestamp is None:
            continue
        groups.setdefault((row.line_id, row.direction), []).append(row.timestamp)

    all_gaps: List[float] = []
    per_group = []
    for (line_id, direction), timestamps in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        timestamps.sort()
        gaps = [
            (timestamps[i] - timestamps[i - 1]).total_seconds()
            for i in range(1, len(timestamps))
        ]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        all_gaps.extend(gaps)
        per_group.append({
            "line_id": line_id,
            "direction": direction,
            "vehicle_count": len(timestamps),
            "headway_count": len(gaps),
            "mean_headway_seconds": round(mean(gaps), 3),
            "median_headway_seconds": round(median(gaps), 3),
        })

    histogram = _headway_histogram(all_gaps)
    critical = sum(1 for g in all_gaps if g < _CRITICAL_HEADWAY_SECONDS)
    return {
        "camera_id": camera_id,
        "headway_count": len(all_gaps),
        "mean_headway_seconds": round(mean(all_gaps), 3) if all_gaps else None,
        "median_headway_seconds": round(median(all_gaps), 3) if all_gaps else None,
        "p15_headway_seconds": _percentile(sorted(all_gaps), 0.15),
        "short_headway_share": round(critical / len(all_gaps), 4) if all_gaps else None,
        "short_headway_threshold_seconds": _CRITICAL_HEADWAY_SECONDS,
        "histogram": histogram,
        "by_line_direction": per_group,
    }


def _headway_histogram(gaps: List[float]) -> List[dict]:
    buckets = []
    lower = 0.0
    for upper in _HEADWAY_BUCKETS:
        buckets.append({
            "range": f"{lower:g}-{upper:g}s",
            "count": sum(1 for g in gaps if lower <= g < upper),
        })
        lower = upper
    buckets.append({"range": f">{lower:g}s", "count": sum(1 for g in gaps if g >= lower)})
    return buckets


def _percentile(sorted_values: List[float], ratio: float) -> Optional[float]:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * ratio)))
    return round(sorted_values[index], 3)


# ---------------------------------------------------------------------------
# Speed compliance
# ---------------------------------------------------------------------------

def _get_speed_compliance_data(db, camera_id, start, end, windows) -> dict:
    speed_limit = None
    if camera_id:
        profile = _get_camera_profile(db, camera_id)
        if profile is not None:
            speed_limit = profile.get("speed_limit_kmh")
    if speed_limit is None:
        import os
        speed_limit = float(os.getenv("DEFAULT_SPEED_LIMIT_KMH", "60.0"))
    speed_limit = float(speed_limit)

    rows = _scoped_query(db, models.DBSpeed, camera_id, start, end, windows).all()
    speeds = [row.speed_kmh for row in rows if row.speed_kmh is not None]
    total = len(speeds)
    within = sum(1 for s in speeds if s <= speed_limit)
    exceedances = [s - speed_limit for s in speeds if s > speed_limit]
    return {
        "camera_id": camera_id,
        "speed_limit_kmh": speed_limit,
        "samples": total,
        "within_limit": within,
        "over_limit": total - within,
        "compliance_rate": round(within / total, 4) if total else None,
        "mean_exceedance_kmh": round(mean(exceedances), 2) if exceedances else None,
        "max_exceedance_kmh": round(max(exceedances), 2) if exceedances else None,
    }


# ---------------------------------------------------------------------------
# Scene condition schema
# ---------------------------------------------------------------------------

class SceneConditionInput(BaseModel):
    start: datetime
    end: datetime
    lighting: Optional[str] = Field(default=None)
    weather: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)


def _serialize_condition(row: models.DBSceneCondition) -> dict:
    return {
        "id": row.id,
        "camera_id": row.camera_id,
        "start": _serialize_dt(row.start),
        "end": _serialize_dt(row.end),
        "lighting": row.lighting,
        "weather": row.weather,
        "notes": row.notes,
        "created_at": _serialize_dt(row.created_at),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/analytics/traffic-profile")
def get_traffic_profile(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    lighting: str = Query(default=None),
    weather: str = Query(default=None),
    db: Session = Depends(get_db),
):
    windows = _matching_condition_windows(db, camera_id, lighting, weather)
    return _get_traffic_profile_data(db, camera_id, start, end, windows)


@router.get("/analytics/headways")
def get_headways(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    lighting: str = Query(default=None),
    weather: str = Query(default=None),
    db: Session = Depends(get_db),
):
    windows = _matching_condition_windows(db, camera_id, lighting, weather)
    return _get_headways_data(db, camera_id, start, end, windows)


@router.get("/analytics/speed-compliance")
def get_speed_compliance(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    lighting: str = Query(default=None),
    weather: str = Query(default=None),
    db: Session = Depends(get_db),
):
    windows = _matching_condition_windows(db, camera_id, lighting, weather)
    return _get_speed_compliance_data(db, camera_id, start, end, windows)


@router.post("/cameras/{camera_id}/conditions", status_code=201)
def create_scene_condition(camera_id: str, payload: SceneConditionInput, db: Session = Depends(get_db)):
    if payload.lighting is not None and payload.lighting not in LIGHTING_VALUES:
        raise HTTPException(status_code=400, detail=f"lighting must be one of {sorted(LIGHTING_VALUES)}")
    if payload.weather is not None and payload.weather not in WEATHER_VALUES:
        raise HTTPException(status_code=400, detail=f"weather must be one of {sorted(WEATHER_VALUES)}")
    if payload.lighting is None and payload.weather is None:
        raise HTTPException(status_code=400, detail="at least one of lighting or weather is required")
    if payload.end <= payload.start:
        raise HTTPException(status_code=400, detail="end must be after start")
    row = models.DBSceneCondition(
        camera_id=camera_id,
        start=payload.start,
        end=payload.end,
        lighting=payload.lighting,
        weather=payload.weather,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_condition(row)


@router.get("/cameras/{camera_id}/conditions")
def list_scene_conditions(camera_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(models.DBSceneCondition)
        .filter(models.DBSceneCondition.camera_id == camera_id)
        .order_by(models.DBSceneCondition.start)
        .all()
    )
    return {"camera_id": camera_id, "conditions": [_serialize_condition(row) for row in rows]}


@router.delete("/cameras/{camera_id}/conditions/{condition_id}")
def delete_scene_condition(camera_id: str, condition_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(models.DBSceneCondition)
        .filter(
            models.DBSceneCondition.id == condition_id,
            models.DBSceneCondition.camera_id == camera_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Scene condition not found")
    db.delete(row)
    db.commit()
    return {"message": "Scene condition deleted", "id": condition_id}
