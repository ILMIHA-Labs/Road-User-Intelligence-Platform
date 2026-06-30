"""FastAPI application factory and startup."""
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import SessionLocal, engine, init_db
from .routes import (
    analytics_router,
    cameras_router,
    exports_router,
    ingest_router,
    live_router,
    trends_router,
    video_analysis_router,
    violations_router,
)
from .routes.cameras import _seed_camera_registry, _upsert_camera_profile
from .routes.video_analysis import _analyze_uploaded_video, _cleanup_video_analysis_jobs, _recover_video_analysis_jobs
from .routes._config import (
    _CAMERAS_CONFIG_PATH,
    _EVIDENCE_CAPTURE_ENABLED,
    _LIVE_CLIP_RETENTION_SECONDS,
    _LIVE_CLIPS_DIR,
    _LIVE_FRAMES_DIR,
    _LIVE_PREVIEW_RETENTION_SECONDS,
    _SETUP_PREVIEW_DIR,
    _SETUP_PREVIEW_RETENTION_SECONDS,
    _VIDEO_ANALYSIS_DIR,
    _VIDEO_ANALYSIS_MAX_UPLOAD_MB,
    _VIDEO_ANALYSIS_RETENTION_SECONDS,
    _VIOLATION_EVIDENCE_DIR,
    _VIOLATION_EVIDENCE_RETENTION_SECONDS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BackendAPI")

_API_KEY = os.getenv("RUIP_API_KEY", "")
_bearer_scheme = HTTPBearer(auto_error=False)


def _require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> None:
    """Validate bearer API key when RUIP_API_KEY is set. No-op when unset (dev mode)."""
    if not _API_KEY:
        return
    if credentials is None or credentials.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


app = FastAPI(
    title="Road User Intelligence Platform API",
    dependencies=[Depends(_require_api_key)],
)

dashboard_dir = Path(__file__).resolve().parents[1] / "dashboard" / "app"
if dashboard_dir.exists():
    from starlette.staticfiles import StaticFiles
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


def _cleanup_dir_older_than(root: Path, retention_seconds: int, label: str):
    if retention_seconds <= 0:
        return
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    for path in (p for p in root.rglob("*") if p.is_file()) if root.exists() else []:
        try:
            if now - path.stat().st_mtime > retention_seconds:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    if removed:
        logger.info("Removed %s expired %s file(s) from %s", removed, label, root)


def _cleanup_runtime_artifacts():
    _cleanup_dir_older_than(_VIOLATION_EVIDENCE_DIR, _VIOLATION_EVIDENCE_RETENTION_SECONDS, "evidence")
    _cleanup_dir_older_than(_LIVE_FRAMES_DIR, _LIVE_PREVIEW_RETENTION_SECONDS, "live preview")
    _cleanup_dir_older_than(_LIVE_CLIPS_DIR, _LIVE_CLIP_RETENTION_SECONDS, "live clip")
    _cleanup_dir_older_than(_SETUP_PREVIEW_DIR, _SETUP_PREVIEW_RETENTION_SECONDS, "setup preview")


@app.on_event("startup")
def startup_event():
    init_db()
    db = SessionLocal()
    try:
        _seed_camera_registry(db)
        _recover_video_analysis_jobs(db)
        _cleanup_video_analysis_jobs(db)
    finally:
        db.close()
    _cleanup_runtime_artifacts()


@app.get("/", dependencies=[])
def read_root():
    return {"status": "MVP API is running"}


@app.get("/health", dependencies=[])
def health_check():
    return {"status": "ok"}


_V1 = "/api/v1"

_ROUTERS = [
    ingest_router,
    cameras_router,
    video_analysis_router,
    violations_router,
    analytics_router,
    trends_router,
    exports_router,
    live_router,
]

for _router in _ROUTERS:
    app.include_router(_router, prefix=_V1)
    app.include_router(_router, include_in_schema=False)
