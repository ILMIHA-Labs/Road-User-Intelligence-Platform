"""Week-over-week / month-over-month trend analytics with rolling-baseline anomaly detection."""
import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ._shared import _daily_counts

logger = logging.getLogger(__name__)
router = APIRouter()

_METRIC_MODELS = {
    "detections": (models.DBDetection, "total_detections_logged"),
    "speeds": (models.DBSpeed, "total_speeds_logged"),
    "violations": (models.DBViolation, "total_violations_logged"),
    "crossings": (models.DBCrossing, "total_crossings_logged"),
}


# ---------------------------------------------------------------------------
# Period bucketing
# ---------------------------------------------------------------------------

def _resolve_periods(
    period: str, reference_date: datetime, baseline_periods: int,
) -> Tuple[Tuple[date, date], Tuple[date, date], List[Tuple[date, date]]]:
    """Return (current_window, previous_window, baseline_windows oldest->newest).

    Windows are half-open [start, end) date ranges so adjacent windows never overlap.
    """
    ref_date = reference_date.date()
    windows: List[Tuple[date, date]] = []
    if period == "week":
        length = timedelta(days=7)
        current_end = ref_date + timedelta(days=1)
        current_start = current_end - length
        cursor_end = current_start
        for _ in range(baseline_periods + 1):
            cursor_start = cursor_end - length
            windows.append((cursor_start, cursor_end))
            cursor_end = cursor_start
    else:  # month
        current_start = ref_date.replace(day=1)
        current_end = ref_date + timedelta(days=1)
        cursor_end = current_start
        for _ in range(baseline_periods + 1):
            if cursor_end.month == 1:
                cursor_start = cursor_end.replace(year=cursor_end.year - 1, month=12, day=1)
            else:
                cursor_start = cursor_end.replace(month=cursor_end.month - 1, day=1)
            windows.append((cursor_start, cursor_end))
            cursor_end = cursor_start

    current = (current_start, current_end)
    previous = windows[0]
    baseline = list(reversed(windows[1:]))
    return current, previous, baseline


def _sum_window(daily_counts: Dict[str, int], start: date, end: date) -> int:
    total = 0
    day = start
    while day < end:
        total += daily_counts.get(day.isoformat(), 0)
        day += timedelta(days=1)
    return total


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def _zscore(current_value: float, baseline_values: List[float]) -> Optional[float]:
    """Sample z-score of current_value against baseline_values.

    Returns None when the baseline has fewer than 2 samples, or when the
    baseline has zero variance but current_value matches it exactly (z=0
    is returned in that exact-match case instead).
    """
    if len(baseline_values) < 2:
        return None
    mean = statistics.mean(baseline_values)
    stddev = statistics.stdev(baseline_values)
    if stddev == 0:
        return 0.0 if current_value == mean else None
    return (current_value - mean) / stddev


# ---------------------------------------------------------------------------
# Trend data helpers
# ---------------------------------------------------------------------------

def _build_metric_trend(
    db: Session,
    model,
    camera_id: Optional[str],
    period: str,
    reference_date: datetime,
    baseline_periods: int,
    z_threshold: float,
    include_history: bool = False,
) -> dict:
    current, previous, baseline = _resolve_periods(period, reference_date, baseline_periods)
    lookback_start_date = baseline[0][0] if baseline else previous[0]
    lookback_start = datetime.combine(lookback_start_date, datetime.min.time(), tzinfo=timezone.utc)
    lookback_end = datetime.combine(current[1], datetime.min.time(), tzinfo=timezone.utc)

    daily = _daily_counts(db, model, camera_id, lookback_start, lookback_end)

    current_value = _sum_window(daily, *current)
    previous_value = _sum_window(daily, *previous)
    baseline_values = [_sum_window(daily, start, end) for start, end in baseline]

    delta = current_value - previous_value
    delta_pct = round((delta / previous_value) * 100, 2) if previous_value else None

    baseline_sample_size = len(baseline_values)
    if baseline_sample_size >= 2:
        baseline_mean = round(statistics.mean(baseline_values), 2)
        baseline_stddev = round(statistics.stdev(baseline_values), 2)
    else:
        baseline_mean = None
        baseline_stddev = None

    z = _zscore(current_value, baseline_values)
    if baseline_sample_size < 2:
        is_anomaly = False
    elif z is None:
        # Zero-variance baseline that the current value does not match — flag as anomalous
        # even though a finite z-score cannot be computed.
        is_anomaly = current_value != (baseline_values[0] if baseline_values else current_value)
    else:
        is_anomaly = abs(z) > z_threshold

    trend = {
        "current": current_value,
        "previous": previous_value,
        "delta": delta,
        "delta_pct": delta_pct,
        "baseline_mean": baseline_mean,
        "baseline_stddev": baseline_stddev,
        "baseline_sample_size": baseline_sample_size,
        "z_score": round(z, 2) if z is not None else None,
        "is_anomaly": is_anomaly,
    }
    if include_history:
        windows_with_values = list(zip(baseline, baseline_values)) + [(previous, previous_value), (current, current_value)]
        trend["history"] = [
            {"period_start": start.isoformat(), "period_end": end.isoformat(), "value": value}
            for (start, end), value in windows_with_values
        ]
    return trend


def _get_trends_summary_data(
    db: Session,
    period: str,
    camera_id: Optional[str],
    reference_date: datetime,
    baseline_periods: int,
    z_threshold: float,
) -> dict:
    current, previous, _ = _resolve_periods(period, reference_date, baseline_periods)
    metrics = {
        metric_key: _build_metric_trend(db, model, camera_id, period, reference_date, baseline_periods, z_threshold)
        for model, metric_key in _METRIC_MODELS.values()
    }
    return {
        "camera_id": camera_id,
        "period": period,
        "reference_date": reference_date.isoformat(),
        "current_period": {"start": current[0].isoformat(), "end": current[1].isoformat()},
        "comparison_period": {"start": previous[0].isoformat(), "end": previous[1].isoformat()},
        "baseline_periods": baseline_periods,
        "z_threshold": z_threshold,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/analytics/trends/summary")
def get_trends_summary(
    period: str = Query(default="week", pattern="^(week|month)$"),
    camera_id: str = Query(default=None),
    reference_date: datetime = Query(default=None),
    baseline_periods: int = Query(default=6, ge=1, le=24),
    z_threshold: float = Query(default=2.0, ge=0.5, le=5.0),
    db: Session = Depends(get_db),
):
    reference_date = reference_date or datetime.now(timezone.utc)
    return _get_trends_summary_data(db, period, camera_id, reference_date, baseline_periods, z_threshold)


@router.get("/analytics/trends/{metric}")
def get_trend_metric(
    metric: str,
    period: str = Query(default="week", pattern="^(week|month)$"),
    camera_id: str = Query(default=None),
    reference_date: datetime = Query(default=None),
    baseline_periods: int = Query(default=6, ge=1, le=24),
    z_threshold: float = Query(default=2.0, ge=0.5, le=5.0),
    db: Session = Depends(get_db),
):
    if metric not in _METRIC_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown trend metric '{metric}'")
    model, metric_key = _METRIC_MODELS[metric]
    reference_date = reference_date or datetime.now(timezone.utc)
    trend = _build_metric_trend(
        db, model, camera_id, period, reference_date, baseline_periods, z_threshold, include_history=True,
    )
    trend["metric"] = metric_key
    trend["camera_id"] = camera_id
    trend["period"] = period
    return trend
