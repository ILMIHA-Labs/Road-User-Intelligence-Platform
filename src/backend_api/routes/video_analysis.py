"""Video analysis upload, job management, and artifact routes."""
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import FileResponse
from uuid import uuid4

import sys as _sys

from .. import models
from ..database import SessionLocal, get_db
from ._config import (
    _VIDEO_ANALYSIS_ALLOWED_EXTENSIONS,
    _VIDEO_ANALYSIS_ARTIFACTS,
    _VIDEO_ANALYSIS_EXECUTOR,
)
from ._shared import _serialize_dt
from .cameras import SetupCountingLineInput, SetupZebraZoneInput, _normalize_setup_counting_lines, _normalize_setup_zebra_zones, _sanitize_camera_id

logger = logging.getLogger(__name__)
router = APIRouter()


def _m():
    """Return the main app module so tests can patch its runtime config."""
    return _sys.modules["backend_api.main"]


class VideoAnalysisRunRequest(BaseModel):
    counting_lines: List[SetupCountingLineInput] = Field(default_factory=list)
    zebra_zones: List[SetupZebraZoneInput] = Field(default_factory=list)
    pixels_per_meter: float = Field(default=25.0, gt=0)
    zebra_speed_threshold_kmh: float = Field(default=15.0, ge=0)
    approach_deadband_kmh: float = Field(default=2.0, ge=0)


# ---------------------------------------------------------------------------
# Job path helpers
# ---------------------------------------------------------------------------

def _video_analysis_job_dir(job_id: str) -> Path:
    return _m()._VIDEO_ANALYSIS_DIR / job_id


def _video_analysis_source_path(job: models.DBVideoAnalysisJob) -> Path:
    return Path(job.artifact_dir) / f"source{job.source_extension}"


def _video_analysis_preview_path(job: models.DBVideoAnalysisJob) -> Path:
    return Path(job.artifact_dir) / "preview.jpg"


def _get_video_analysis_job(db: Session, job_id: str) -> models.DBVideoAnalysisJob:
    job = db.query(models.DBVideoAnalysisJob).filter(models.DBVideoAnalysisJob.job_id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return job


def _ensure_video_analysis_available(job: models.DBVideoAnalysisJob):
    if job.status in {"deleted", "expired"}:
        raise HTTPException(status_code=410, detail="Analysis session is no longer available.")


def _video_analysis_has_zebra_layer(job: models.DBVideoAnalysisJob) -> bool:
    return bool((job.setup or {}).get("zebra_zones"))


def _video_analysis_public_artifacts(job: models.DBVideoAnalysisJob) -> dict:
    if _video_analysis_has_zebra_layer(job):
        return _VIDEO_ANALYSIS_ARTIFACTS
    return {
        name: artifact
        for name, artifact in _VIDEO_ANALYSIS_ARTIFACTS.items()
        if name not in {
            "zebra_events_csv", "zebra_occupancy_csv",
            "pedestrian_episodes_csv", "yielding_events_csv", "pet_events_csv",
        }
    }


def _video_analysis_artifact_urls(job: models.DBVideoAnalysisJob) -> dict:
    if job.status != "completed":
        return {}
    return {
        name: f"/video-analysis/jobs/{job.job_id}/artifacts/{name}"
        for name, (filename, _) in _video_analysis_public_artifacts(job).items()
        if (Path(job.artifact_dir) / filename).exists()
    }


def _serialize_video_analysis_job(job: models.DBVideoAnalysisJob) -> dict:
    is_available = job.status not in {"deleted", "expired"}
    preview_available = is_available and _video_analysis_preview_path(job).exists()
    return {
        "job_id": job.job_id,
        "label": job.label,
        "camera_id": job.camera_id,
        "original_filename": job.original_filename,
        "upload_size_bytes": job.upload_size_bytes,
        "status": job.status,
        "processed_frames": job.processed_frames,
        "total_frames": job.total_frames,
        "progress_percent": round(float(job.progress_percent or 0.0), 1),
        "failure_message": job.failure_message,
        "setup": job.setup or {},
        "preview_width": job.preview_width,
        "preview_height": job.preview_height,
        "preview_url": f"/video-analysis/jobs/{job.job_id}/preview" if preview_available else None,
        "artifacts": _video_analysis_artifact_urls(job),
        "result_summary": job.result_summary if job.status == "completed" else None,
        "created_at": _serialize_dt(job.created_at),
        "started_at": _serialize_dt(job.started_at),
        "completed_at": _serialize_dt(job.completed_at),
        "expires_at": _serialize_dt(job.expires_at),
    }


def _cleanup_video_analysis_jobs(db: Session):
    now = datetime.now(timezone.utc)
    jobs = (
        db.query(models.DBVideoAnalysisJob)
        .filter(
            models.DBVideoAnalysisJob.expires_at <= now,
            models.DBVideoAnalysisJob.status.notin_(("deleted", "expired")),
        )
        .all()
    )
    for job in jobs:
        shutil.rmtree(job.artifact_dir, ignore_errors=True)
        job.status = "expired"
        job.result_summary = None
        job.failure_message = "Temporary analysis files expired."
        job.completed_at = now
    if jobs:
        db.commit()


def _recover_video_analysis_jobs(db: Session):
    interrupted = db.query(models.DBVideoAnalysisJob).filter(
        models.DBVideoAnalysisJob.status.in_(("queued", "running"))
    ).all()
    now = datetime.now(timezone.utc)
    for job in interrupted:
        job.status = "failed"
        job.failure_message = "Analysis interrupted by server restart. Start a new run."
        job.completed_at = now
    if interrupted:
        db.commit()


def _public_video_analysis_summary(job: models.DBVideoAnalysisJob, summary: dict) -> dict:
    public_summary = dict(summary or {})
    public_video = dict(public_summary.get("video") or {})
    public_video["path"] = job.original_filename
    public_summary["video"] = public_video
    if not _video_analysis_has_zebra_layer(job):
        public_summary.pop("zebra_metrics", None)
        public_summary.pop("zebra_zones", None)
    public_summary["outputs"] = {
        name: f"/video-analysis/jobs/{job.job_id}/artifacts/{name}"
        for name in _video_analysis_public_artifacts(job)
    }
    return public_summary


def _analyze_uploaded_video(job: models.DBVideoAnalysisJob, progress_callback):
    from video_analysis.traffic_metrics import TrafficMetricsAnalyzer, YoloTrackDetector

    setup = job.setup or {}
    camera_profile = {
        "pixels_per_meter": setup.get("pixels_per_meter", 25.0),
        "counting_lines": setup.get("counting_lines", []),
        "zones": setup.get("zebra_zones", []),
    }
    analyzer = TrafficMetricsAnalyzer(
        camera_id=job.camera_id,
        camera_profile=camera_profile,
        detector=YoloTrackDetector(model_path="yolov8l.pt", confidence=0.25),
        counting_lines=setup.get("counting_lines", []),
        zebra_zones=setup.get("zebra_zones", []),
        pixels_per_meter=setup.get("pixels_per_meter", 25.0),
        zebra_speed_threshold_kmh=setup.get("zebra_speed_threshold_kmh", 15.0),
        zebra_zone_margin_m=2.0,
        zebra_interaction_window_seconds=3.0,
        zebra_speed_trend_deadband_kmh=setup.get("zebra_speed_trend_deadband_kmh", 2.0),
        filter_riders_from_pedestrians=True,
    )
    return analyzer.analyze_video(
        str(_video_analysis_source_path(job)),
        job.artifact_dir,
        show_progress=False,
        progress_callback=progress_callback,
    )


def _execute_video_analysis_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(models.DBVideoAnalysisJob).filter(models.DBVideoAnalysisJob.job_id == job_id).first()
        if job is None or job.status != "queued":
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        last_percent = -1.0

        def update_progress(processed_frames: int, total_frames: int):
            nonlocal last_percent
            percent = round((processed_frames / total_frames) * 100.0, 1) if total_frames else 0.0
            if processed_frames != total_frames and percent < last_percent + 1.0:
                return
            progress_db = SessionLocal()
            try:
                current = progress_db.query(models.DBVideoAnalysisJob).filter(
                    models.DBVideoAnalysisJob.job_id == job_id,
                    models.DBVideoAnalysisJob.status == "running",
                ).first()
                if current is not None:
                    current.processed_frames = int(processed_frames)
                    current.total_frames = int(total_frames) if total_frames else None
                    current.progress_percent = percent
                    progress_db.commit()
                    last_percent = percent
            finally:
                progress_db.close()

        summary = _m()._analyze_uploaded_video(job, update_progress)
        completed = db.query(models.DBVideoAnalysisJob).filter(
            models.DBVideoAnalysisJob.job_id == job_id,
            models.DBVideoAnalysisJob.status == "running",
        ).first()
        if completed is None:
            return
        public_summary = _public_video_analysis_summary(completed, summary)
        summary_path = Path(completed.artifact_dir) / "summary.json"
        with open(summary_path, "w") as output:
            json.dump(public_summary, output, indent=2)
        completed.status = "completed"
        completed.progress_percent = 100.0
        if completed.total_frames is None:
            completed.total_frames = int(public_summary.get("video", {}).get("processed_frames") or 0)
            completed.processed_frames = completed.total_frames
        completed.result_summary = public_summary
        completed.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as error:
        logger.exception("Video analysis job %s failed", job_id)
        db.rollback()
        failed = db.query(models.DBVideoAnalysisJob).filter(
            models.DBVideoAnalysisJob.job_id == job_id,
            models.DBVideoAnalysisJob.status.in_(("queued", "running")),
        ).first()
        if failed is not None:
            failed.status = "failed"
            failed.failure_message = str(error)[:500] or "Video analysis failed."
            failed.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/video-analysis/uploads", status_code=201)
async def create_video_analysis_upload(
    file: UploadFile = File(...),
    label: str = Form(default=""),
    camera_id: str = Form(default=""),
    db: Session = Depends(get_db),
):
    _cleanup_video_analysis_jobs(db)
    original_filename = Path(file.filename or "upload").name
    extension = Path(original_filename).suffix.lower()
    if extension not in _VIDEO_ANALYSIS_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format. Upload an .mp4, .mov, .avi, .mkv, or .webm file.",
        )

    job_id = uuid4().hex
    job_dir = _video_analysis_job_dir(job_id)
    source_path = job_dir / f"source{extension}"
    max_size_bytes = max(0, _m()._VIDEO_ANALYSIS_MAX_UPLOAD_MB) * 1024 * 1024
    size_bytes = 0
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(source_path, "wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds the {_m()._VIDEO_ANALYSIS_MAX_UPLOAD_MB} MB temporary analysis limit.",
                    )
                output.write(chunk)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        await file.close()

    if size_bytes <= 0:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Uploaded video is empty.")

    capture = cv2.VideoCapture(str(source_path))
    try:
        readable, frame = capture.read()
    finally:
        capture.release()
    if not readable or frame is None:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Unable to read the uploaded video.")

    preview_path = job_dir / "preview.jpg"
    if not cv2.imwrite(str(preview_path), frame):
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Unable to create a preview frame.")

    height, width = frame.shape[:2]
    safe_camera_id = _sanitize_camera_id(camera_id or f"analysis_{job_id[:8]}")
    job = models.DBVideoAnalysisJob(
        job_id=job_id,
        label=(label.strip() or Path(original_filename).stem or safe_camera_id)[:120],
        camera_id=safe_camera_id,
        original_filename=original_filename,
        upload_content_type=file.content_type,
        upload_size_bytes=size_bytes,
        source_extension=extension,
        artifact_dir=str(job_dir),
        preview_width=int(width),
        preview_height=int(height),
        status="draft",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(1, _m()._VIDEO_ANALYSIS_RETENTION_SECONDS)),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_video_analysis_job(job)


@router.get("/video-analysis/jobs")
def list_video_analysis_jobs(db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    rows = (
        db.query(models.DBVideoAnalysisJob)
        .filter(models.DBVideoAnalysisJob.status.notin_(("deleted", "expired")))
        .order_by(models.DBVideoAnalysisJob.created_at.desc())
        .limit(50)
        .all()
    )
    return {"jobs": [_serialize_video_analysis_job(row) for row in rows]}


@router.get("/video-analysis/jobs/{job_id}")
def get_video_analysis_job(job_id: str, db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    job = _get_video_analysis_job(db, job_id)
    _ensure_video_analysis_available(job)
    return _serialize_video_analysis_job(job)


@router.get("/video-analysis/jobs/{job_id}/preview")
def get_video_analysis_preview(job_id: str, db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    job = _get_video_analysis_job(db, job_id)
    _ensure_video_analysis_available(job)
    preview_path = _video_analysis_preview_path(job)
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Analysis preview is unavailable.")
    return FileResponse(preview_path, media_type="image/jpeg")


@router.post("/video-analysis/jobs/{job_id}/run", status_code=202)
def run_video_analysis_job(job_id: str, request: VideoAnalysisRunRequest, db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    job = _get_video_analysis_job(db, job_id)
    _ensure_video_analysis_available(job)
    if job.status not in {"draft", "failed"}:
        raise HTTPException(status_code=409, detail="Only a draft or failed analysis can be submitted.")

    counting_lines = _normalize_setup_counting_lines(request.counting_lines)
    zebra_zones = _normalize_setup_zebra_zones(request.zebra_zones)
    if not counting_lines:
        raise HTTPException(status_code=400, detail="Draw at least one valid counting line before analysis.")
    if not _video_analysis_source_path(job).exists():
        raise HTTPException(status_code=410, detail="The temporary uploaded source is no longer available.")

    for filename, _ in _VIDEO_ANALYSIS_ARTIFACTS.values():
        (Path(job.artifact_dir) / filename).unlink(missing_ok=True)
    job.setup = {
        "counting_lines": counting_lines,
        "zebra_zones": zebra_zones,
        "pixels_per_meter": request.pixels_per_meter,
        "zebra_speed_threshold_kmh": request.zebra_speed_threshold_kmh,
        "zebra_speed_trend_deadband_kmh": request.approach_deadband_kmh,
    }
    job.status = "queued"
    job.processed_frames = 0
    job.total_frames = None
    job.progress_percent = 0.0
    job.started_at = None
    job.completed_at = None
    job.failure_message = None
    job.result_summary = None
    db.commit()
    db.refresh(job)
    _VIDEO_ANALYSIS_EXECUTOR.submit(_execute_video_analysis_job, job.job_id)
    return _serialize_video_analysis_job(job)


@router.get("/video-analysis/jobs/{job_id}/artifacts/{artifact_name}")
def get_video_analysis_artifact(job_id: str, artifact_name: str, db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    job = _get_video_analysis_job(db, job_id)
    _ensure_video_analysis_available(job)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis artifacts are available only after completion.")
    artifact = _video_analysis_public_artifacts(job).get(artifact_name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Analysis artifact not found.")
    filename, media_type = artifact
    artifact_path = Path(job.artifact_dir) / filename
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Analysis artifact not found.")
    return FileResponse(artifact_path, media_type=media_type, filename=filename)


@router.delete("/video-analysis/jobs/{job_id}")
def delete_video_analysis_job(job_id: str, db: Session = Depends(get_db)):
    _cleanup_video_analysis_jobs(db)
    job = _get_video_analysis_job(db, job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="A running analysis cannot be deleted.")
    if job.status in {"deleted", "expired"}:
        raise HTTPException(status_code=410, detail="Analysis session is no longer available.")
    shutil.rmtree(job.artifact_dir, ignore_errors=True)
    job.status = "deleted"
    job.result_summary = None
    job.failure_message = "Deleted by user."
    db.commit()
    return {"job_id": job.job_id, "status": job.status}
