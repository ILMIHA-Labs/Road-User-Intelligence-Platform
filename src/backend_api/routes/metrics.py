"""Prometheus-style text-exposition metrics for operational monitoring."""
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import Response

from .. import models
from ..database import get_db

router = APIRouter()

_START_TIME = time.monotonic()

_COUNTER_METRICS = (
    ("ruip_detections_total", "Total road-user detections recorded.", models.DBDetection),
    ("ruip_speed_samples_total", "Total speed samples recorded.", models.DBSpeed),
    ("ruip_violations_total", "Total safety violations recorded.", models.DBViolation),
    ("ruip_crossings_total", "Total line-crossing events recorded.", models.DBCrossing),
)


@router.get("/metrics", dependencies=[])
def get_metrics(db: Session = Depends(get_db)):
    """Expose basic operational counters in Prometheus text-exposition format."""
    lines = []
    for name, help_text, model in _COUNTER_METRICS:
        count = db.query(model).count()
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {count}")

    uptime_seconds = time.monotonic() - _START_TIME
    lines.append("# HELP ruip_uptime_seconds Seconds since the backend process started.")
    lines.append("# TYPE ruip_uptime_seconds gauge")
    lines.append(f"ruip_uptime_seconds {uptime_seconds:.3f}")

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
