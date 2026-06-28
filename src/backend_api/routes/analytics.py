"""Analytics query routes and their data helpers."""
import logging
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ._shared import (
    _apply_camera_filter,
    _apply_supported_violation_filter,
    _apply_time_filters,
    _serialize_detection_class_rows,
    _serialize_recent_crossings,
    _serialize_recent_detections,
    _serialize_recent_speeds,
    _serialize_recent_violations,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Analytics data helpers
# ---------------------------------------------------------------------------

def _build_counts_map(items, key_field="count", label_field=None):
    counts = {}
    for item in items:
        label = item.get(label_field or "class") or item.get("direction") or item.get("line_id")
        if label:
            counts[label] = item.get(key_field, 0)
    return counts


def _p85(values):
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.85)))
    return sorted_values[index]


def _resolve_flow_rate_per_minute(start, end, min_timestamp, max_timestamp, total_crossings):
    if total_crossings <= 0:
        return 0.0
    if start is not None and end is not None and end > start:
        duration_seconds = (end - start).total_seconds()
    elif min_timestamp is not None and max_timestamp is not None and max_timestamp > min_timestamp:
        duration_seconds = (max_timestamp - min_timestamp).total_seconds()
    else:
        return 0.0
    duration_minutes = duration_seconds / 60.0
    if duration_minutes <= 0:
        return 0.0
    return round(total_crossings / duration_minutes, 2)


def _get_analytics_summary_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    detection_query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBDetection), models.DBDetection, camera_id),
        models.DBDetection, start, end,
    )
    violation_query = _apply_time_filters(
        _apply_camera_filter(
            _apply_supported_violation_filter(db.query(models.DBViolation)),
            models.DBViolation, camera_id,
        ),
        models.DBViolation, start, end,
    )
    speed_query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBSpeed), models.DBSpeed, camera_id),
        models.DBSpeed, start, end,
    )
    crossing_query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBCrossing), models.DBCrossing, camera_id),
        models.DBCrossing, start, end,
    )
    detection_class_rows = (
        detection_query
        .with_entities(models.DBDetection.class_name, func.count(models.DBDetection.id).label("count"))
        .group_by(models.DBDetection.class_name)
        .all()
    )
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_detections_logged": detection_query.count(),
        "total_speeds_logged": speed_query.count(),
        "total_violations_logged": violation_query.count(),
        "total_crossings_logged": crossing_query.count(),
        "detection_classes": _serialize_detection_class_rows(detection_class_rows),
    }


def _get_detection_analytics_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBDetection), models.DBDetection, camera_id),
        models.DBDetection, start, end,
    )
    class_rows = (
        query.with_entities(models.DBDetection.class_name, func.count(models.DBDetection.id).label("count"))
        .group_by(models.DBDetection.class_name).all()
    )
    camera_rows = (
        query.with_entities(
            models.DBDetection.camera_id,
            models.DBDetection.class_name,
            func.count(models.DBDetection.id).label("count"),
        )
        .group_by(models.DBDetection.camera_id, models.DBDetection.class_name).all()
    )
    cameras = {}
    for row in camera_rows:
        camera = cameras.setdefault(row.camera_id, {"camera_id": row.camera_id, "total_detections": 0, "classes": []})
        camera["classes"].append({"class": row.class_name, "count": row.count})
        camera["total_detections"] += row.count
    for camera in cameras.values():
        camera["classes"].sort(key=lambda item: (-item["count"], item["class"]))
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_detections": query.count(),
        "classes": _serialize_detection_class_rows(class_rows),
        "cameras": sorted(cameras.values(), key=lambda item: item["camera_id"]),
    }


def _get_analytics_by_camera_data(db: Session, start: datetime = None, end: datetime = None):
    detection_rows = (
        _apply_time_filters(
            db.query(models.DBDetection.camera_id, func.count(models.DBDetection.id).label("detections")),
            models.DBDetection, start, end,
        ).group_by(models.DBDetection.camera_id).all()
    )
    speed_rows = (
        _apply_time_filters(
            db.query(models.DBSpeed.camera_id, func.count(models.DBSpeed.id).label("speeds")),
            models.DBSpeed, start, end,
        ).group_by(models.DBSpeed.camera_id).all()
    )
    violation_rows = (
        _apply_time_filters(
            _apply_supported_violation_filter(
                db.query(models.DBViolation.camera_id, func.count(models.DBViolation.id).label("violations"))
            ),
            models.DBViolation, start, end,
        ).group_by(models.DBViolation.camera_id).all()
    )
    crossing_rows = (
        _apply_time_filters(
            db.query(models.DBCrossing.camera_id, func.count(models.DBCrossing.id).label("crossings")),
            models.DBCrossing, start, end,
        ).group_by(models.DBCrossing.camera_id).all()
    )
    summary = {}
    for row in detection_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["detections"] = row.detections
    for row in speed_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["speeds"] = row.speeds
    for row in violation_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["violations"] = row.violations
    for row in crossing_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["crossings"] = row.crossings
    return {"start": start, "end": end, "cameras": sorted(summary.values(), key=lambda item: item["camera_id"])}


def _get_violation_breakdown_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = _apply_time_filters(
        _apply_camera_filter(
            _apply_supported_violation_filter(
                db.query(models.DBViolation.violation_type, func.count(models.DBViolation.id).label("count"))
            ),
            models.DBViolation, camera_id,
        ),
        models.DBViolation, start, end,
    ).group_by(models.DBViolation.violation_type).all()
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "violations": [{"violation_type": row.violation_type, "count": row.count} for row in query],
    }


def _get_crossing_analytics_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBCrossing), models.DBCrossing, camera_id),
        models.DBCrossing, start, end,
    )
    total_crossings = query.count()
    min_timestamp, max_timestamp = query.with_entities(
        func.min(models.DBCrossing.timestamp), func.max(models.DBCrossing.timestamp)
    ).one()
    direction_rows = (
        query.with_entities(models.DBCrossing.direction, func.count(models.DBCrossing.id).label("count"))
        .group_by(models.DBCrossing.direction).all()
    )
    class_rows = (
        query.with_entities(models.DBCrossing.class_name, func.count(models.DBCrossing.id).label("count"))
        .group_by(models.DBCrossing.class_name).all()
    )
    line_rows = (
        query.with_entities(
            models.DBCrossing.line_id, models.DBCrossing.line_label,
            models.DBCrossing.direction, func.count(models.DBCrossing.id).label("count"),
        )
        .group_by(models.DBCrossing.line_id, models.DBCrossing.line_label, models.DBCrossing.direction).all()
    )
    lines = {}
    for row in line_rows:
        line = lines.setdefault(row.line_id, {"line_id": row.line_id, "line_label": row.line_label, "count": 0, "directions": {}})
        line["directions"][row.direction] = row.count
        line["count"] += row.count
    crossing_objects = {
        (row.camera_id, row.object_id): row.class_name
        for row in query.with_entities(models.DBCrossing.camera_id, models.DBCrossing.object_id, models.DBCrossing.class_name).all()
    }
    speed_query = _apply_time_filters(
        _apply_camera_filter(db.query(models.DBSpeed), models.DBSpeed, camera_id),
        models.DBSpeed, start, end,
    )
    speeds_by_class: dict = {}
    for row in speed_query.all():
        class_name = crossing_objects.get((row.camera_id, row.object_id))
        if class_name:
            speeds_by_class.setdefault(class_name, []).append(float(row.speed_kmh))
    speed_metrics_by_class = {
        class_name: {
            "avg_speed_kmh": round(sum(values) / len(values), 2),
            "max_speed_kmh": round(max(values), 2),
            "p85_speed_kmh": round(_p85(values), 2) if _p85(values) is not None else None,
            "samples": len(values),
        }
        for class_name, values in sorted(speeds_by_class.items())
    }
    directions = [{"direction": row.direction, "count": row.count} for row in direction_rows]
    classes = [{"class": row.class_name, "count": row.count} for row in class_rows]
    sorted_lines = sorted(lines.values(), key=lambda item: (-item["count"], item["line_id"]))
    return {
        "camera_id": camera_id, "start": start, "end": end,
        "total_crossings": total_crossings,
        "directions": directions, "classes": classes, "lines": sorted_lines,
        "counts_by_direction": {item["direction"]: item["count"] for item in directions},
        "counts_by_class": {item["class"]: item["count"] for item in classes},
        "counts_by_line": {item["line_id"]: item["count"] for item in sorted_lines},
        "flow_rate_per_minute": _resolve_flow_rate_per_minute(start, end, min_timestamp, max_timestamp, total_crossings),
        "speed_metrics_by_class": speed_metrics_by_class,
    }


def _get_recent_events_data(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
    limit: int = 10,
    offset: int = 0,
):
    def _q(model):
        return _apply_time_filters(_apply_camera_filter(db.query(model), model, camera_id), model, start, end)

    detections = _q(models.DBDetection).order_by(models.DBDetection.timestamp.desc()).offset(offset).limit(limit).all()
    speeds = _q(models.DBSpeed).order_by(models.DBSpeed.timestamp.desc()).offset(offset).limit(limit).all()
    violations = (
        _apply_time_filters(
            _apply_camera_filter(_apply_supported_violation_filter(db.query(models.DBViolation)), models.DBViolation, camera_id),
            models.DBViolation, start, end,
        )
        .order_by(models.DBViolation.timestamp.desc()).offset(offset).limit(limit).all()
    )
    crossings = _q(models.DBCrossing).order_by(models.DBCrossing.timestamp.desc()).offset(offset).limit(limit).all()
    return {
        "camera_id": camera_id, "start": start, "end": end,
        "detections": _serialize_recent_detections(detections),
        "speeds": _serialize_recent_speeds(speeds),
        "violations": _serialize_recent_violations(violations),
        "crossings": _serialize_recent_crossings(crossings),
    }


def _get_speed_distribution_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    bands = [
        (0, 20, "0–20"), (20, 40, "20–40"), (40, 60, "40–60"),
        (60, 80, "60–80"), (80, 100, "80–100"), (100, 120, "100–120"), (120, None, "120+"),
    ]
    bucket_expr = case(
        *[(
            (models.DBSpeed.speed_kmh >= lo) & (models.DBSpeed.speed_kmh < hi),
            label,
        ) for lo, hi, label in bands if hi is not None],
        else_="120+",
    )
    query = _apply_time_filters(
        _apply_camera_filter(
            db.query(bucket_expr.label("band"), func.count(models.DBSpeed.id).label("count")),
            models.DBSpeed, camera_id,
        ),
        models.DBSpeed, start, end,
    )
    counts = {row.band: row.count for row in query.group_by(bucket_expr).all()}
    return {
        "camera_id": camera_id, "start": start, "end": end,
        "buckets": [{"band": label, "count": counts.get(label, 0)} for _, _, label in bands],
    }


def _get_violation_log_data(
    db: Session,
    camera_id: str = None,
    violation_type: str = None,
    start: datetime = None,
    end: datetime = None,
    page: int = 1,
    page_size: int = 25,
):
    query = _apply_supported_violation_filter(db.query(models.DBViolation))
    if camera_id:
        query = query.filter(models.DBViolation.camera_id == camera_id)
    if violation_type:
        query = query.filter(models.DBViolation.violation_type == violation_type)
    query = _apply_time_filters(query, models.DBViolation, start, end)
    total = query.count()
    offset = (page - 1) * page_size
    rows = query.order_by(models.DBViolation.timestamp.desc()).offset(offset).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
        "items": _serialize_recent_violations(rows),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/analytics/summary")
def get_analytics_summary(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_analytics_summary_data(db, camera_id, start, end)


@router.get("/analytics/detections")
def get_detection_analytics(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_detection_analytics_data(db, camera_id, start, end)


@router.get("/analytics/by-camera")
def get_analytics_by_camera(
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_analytics_by_camera_data(db, start, end)


@router.get("/analytics/violations")
def get_violation_breakdown(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_violation_breakdown_data(db, camera_id, start, end)


@router.get("/analytics/crossings")
def get_crossing_analytics(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_crossing_analytics_data(db, camera_id, start, end)


@router.get("/events/recent")
def get_recent_events(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return _get_recent_events_data(db, camera_id, start, end, limit, offset)


@router.get("/analytics/speed-distribution")
def get_speed_distribution(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_speed_distribution_data(db, camera_id, start, end)


@router.get("/violations/log")
def get_violations_log(
    camera_id: str = Query(default=None),
    violation_type: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return _get_violation_log_data(db, camera_id, violation_type, start, end, page, page_size)
