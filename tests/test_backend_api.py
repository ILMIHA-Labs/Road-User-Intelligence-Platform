import unittest
from fastapi.testclient import TestClient
import sys
import os
import tempfile
import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

# Ensure src is in the path for importing backend_api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Never let table-reset tests touch an operator's local runtime database.
_TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DATABASE_DIR.name) / 'backend_api_test.db'}"

import backend_api.main as backend_main
from backend_api.database import init_db, SessionLocal
from backend_api.main import app, engine
from backend_api.models import Base, DBViolation, DBVideoAnalysisJob

class TestBackendAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        init_db()
        self.live_preview_tmp = tempfile.TemporaryDirectory()
        self.live_clip_tmp = tempfile.TemporaryDirectory()
        self.evidence_tmp = tempfile.TemporaryDirectory()
        self.config_tmp = tempfile.TemporaryDirectory()
        self.video_analysis_tmp = tempfile.TemporaryDirectory()
        self.original_live_frames_dir = backend_main._LIVE_FRAMES_DIR
        self.original_live_clips_dir = backend_main._LIVE_CLIPS_DIR
        self.original_violation_evidence_dir = backend_main._VIOLATION_EVIDENCE_DIR
        self.original_cameras_config_path = backend_main._CAMERAS_CONFIG_PATH
        self.original_evidence_capture_enabled = backend_main._EVIDENCE_CAPTURE_ENABLED
        self.original_violation_evidence_retention = backend_main._VIOLATION_EVIDENCE_RETENTION_SECONDS
        self.original_live_preview_retention = backend_main._LIVE_PREVIEW_RETENTION_SECONDS
        self.original_live_clip_retention = backend_main._LIVE_CLIP_RETENTION_SECONDS
        self.original_setup_preview_retention = backend_main._SETUP_PREVIEW_RETENTION_SECONDS
        self.original_video_analysis_dir = backend_main._VIDEO_ANALYSIS_DIR
        self.original_video_analysis_retention = backend_main._VIDEO_ANALYSIS_RETENTION_SECONDS
        self.original_video_analysis_max_upload_mb = backend_main._VIDEO_ANALYSIS_MAX_UPLOAD_MB
        backend_main._LIVE_FRAMES_DIR = Path(self.live_preview_tmp.name)
        backend_main._LIVE_CLIPS_DIR = Path(self.live_clip_tmp.name)
        backend_main._VIOLATION_EVIDENCE_DIR = Path(self.evidence_tmp.name)
        backend_main._EVIDENCE_CAPTURE_ENABLED = True
        backend_main._VIOLATION_EVIDENCE_RETENTION_SECONDS = 7 * 24 * 60 * 60
        backend_main._LIVE_PREVIEW_RETENTION_SECONDS = 24 * 60 * 60
        backend_main._LIVE_CLIP_RETENTION_SECONDS = 24 * 60 * 60
        backend_main._SETUP_PREVIEW_RETENTION_SECONDS = 24 * 60 * 60
        backend_main._VIDEO_ANALYSIS_DIR = Path(self.video_analysis_tmp.name)
        backend_main._VIDEO_ANALYSIS_RETENTION_SECONDS = 24 * 60 * 60
        backend_main._VIDEO_ANALYSIS_MAX_UPLOAD_MB = 10
        temp_config_path = Path(self.config_tmp.name) / "cameras.yaml"
        shutil.copy2(self.original_cameras_config_path, temp_config_path)
        backend_main._CAMERAS_CONFIG_PATH = temp_config_path
        self.client_cm = TestClient(app)
        self.client = self.client_cm.__enter__()

    def tearDown(self):
        self.client_cm.__exit__(None, None, None)
        backend_main._LIVE_FRAMES_DIR = self.original_live_frames_dir
        backend_main._LIVE_CLIPS_DIR = self.original_live_clips_dir
        backend_main._VIOLATION_EVIDENCE_DIR = self.original_violation_evidence_dir
        backend_main._CAMERAS_CONFIG_PATH = self.original_cameras_config_path
        backend_main._EVIDENCE_CAPTURE_ENABLED = self.original_evidence_capture_enabled
        backend_main._VIOLATION_EVIDENCE_RETENTION_SECONDS = self.original_violation_evidence_retention
        backend_main._LIVE_PREVIEW_RETENTION_SECONDS = self.original_live_preview_retention
        backend_main._LIVE_CLIP_RETENTION_SECONDS = self.original_live_clip_retention
        backend_main._SETUP_PREVIEW_RETENTION_SECONDS = self.original_setup_preview_retention
        backend_main._VIDEO_ANALYSIS_DIR = self.original_video_analysis_dir
        backend_main._VIDEO_ANALYSIS_RETENTION_SECONDS = self.original_video_analysis_retention
        backend_main._VIDEO_ANALYSIS_MAX_UPLOAD_MB = self.original_video_analysis_max_upload_mb
        self.live_preview_tmp.cleanup()
        self.live_clip_tmp.cleanup()
        self.evidence_tmp.cleanup()
        self.config_tmp.cleanup()
        self.video_analysis_tmp.cleanup()
        Base.metadata.drop_all(bind=engine)

    def test_read_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_metrics_endpoint_exposes_prometheus_counters(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])
        self.assertIn("ruip_violations_total", response.text)
        self.assertIn("ruip_uptime_seconds", response.text)

    def test_dashboard_static_page_serves(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Traffic Operations Dashboard", response.text)
        self.assertNotIn("Refresh Data", response.text)
        self.assertIn("Connecting", response.text)
        self.assertIn("config-search", response.text)
        self.assertIn("config-next-page", response.text)
        self.assertIn("data-mobile-nav", response.text)
        self.assertIn('data-view-button="analysis"', response.text)
        self.assertIn('id="analysis-file"', response.text)
        self.assertIn("Optional Zebra Safety Zone", response.text)

    def _analysis_video_bytes(self):
        path = Path(self.config_tmp.name) / "upload_fixture.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (80, 60))
        for _ in range(3):
            writer.write(np.zeros((60, 80, 3), dtype=np.uint8))
        writer.release()
        return path.read_bytes()

    def _upload_analysis_video(self):
        return self.client.post(
            "/video-analysis/uploads",
            data={"label": "Permitted study clip", "camera_id": "upload_cam"},
            files={"file": ("study.mp4", self._analysis_video_bytes(), "video/mp4")},
        )

    def _fake_analysis_outputs(self, job, progress_callback):
        progress_callback(1, 2)
        progress_callback(2, 2)
        artifact_dir = Path(job.artifact_dir)
        (artifact_dir / "annotated.mp4").write_bytes(b"temporary-annotated-video")
        for filename in ("summary.json", "metrics.json"):
            (artifact_dir / filename).write_text("{}", encoding="utf-8")
        for filename in ("crossings.csv", "zebra_events.csv", "zebra_occupancy.csv", "tracks.csv"):
            (artifact_dir / filename).write_text("id\n", encoding="utf-8")
        return {
            "video": {"path": str(artifact_dir / "source.mp4"), "processed_frames": 2},
            "zebra_zones": [{"id": "generated_zebra"}],
            "metrics": {
                "total_crossings": 1,
                "flow_rate_per_minute": 1.0,
                "counts_by_class": {"car": 1},
                "counts_by_line": {"count_line_1": 1},
                "counts_by_direction": {"a_to_b": 1},
                "speed_metrics_by_class": {},
            },
            "zebra_metrics": {"events": 1, "by_zone": {"zebra_1": {"events": 1}}},
            "outputs": {},
        }

    def test_video_analysis_upload_creates_preview_and_rejects_invalid_media(self):
        response = self._upload_analysis_video()
        self.assertEqual(response.status_code, 201)
        job = response.json()
        self.assertEqual(job["status"], "draft")
        self.assertEqual(job["camera_id"], "upload_cam")
        self.assertNotIn("artifact_dir", job)
        self.assertEqual(self.client.get(job["preview_url"]).headers["content-type"], "image/jpeg")

        unsupported = self.client.post(
            "/video-analysis/uploads",
            files={"file": ("notes.txt", b"not a video", "text/plain")},
        )
        unreadable = self.client.post(
            "/video-analysis/uploads",
            files={"file": ("broken.mp4", b"not a readable video", "video/mp4")},
        )
        self.assertEqual(unsupported.status_code, 400)
        self.assertEqual(unreadable.status_code, 400)
        backend_main._VIDEO_ANALYSIS_MAX_UPLOAD_MB = 0
        try:
            oversized = self._upload_analysis_video()
        finally:
            backend_main._VIDEO_ANALYSIS_MAX_UPLOAD_MB = 10
        self.assertEqual(oversized.status_code, 413)

    def test_video_analysis_run_requires_geometry(self):
        job_id = self._upload_analysis_video().json()["job_id"]
        response = self.client.post(
            f"/video-analysis/jobs/{job_id}/run",
            json={"counting_lines": [], "zebra_zones": [], "pixels_per_meter": 25},
        )
        self.assertEqual(response.status_code, 400)

    def test_video_analysis_completes_in_isolation_and_serves_allowlisted_artifacts(self):
        job_id = self._upload_analysis_video().json()["job_id"]
        original_analyzer = backend_main._analyze_uploaded_video
        backend_main._analyze_uploaded_video = self._fake_analysis_outputs
        try:
            response = self.client.post(
                f"/video-analysis/jobs/{job_id}/run",
                json={
                    "counting_lines": [{"id": "count_line_1", "points": [[1, 1], [20, 20]]}],
                    "zebra_zones": [{"id": "zebra_1", "points": [[2, 2], [30, 2], [30, 20], [2, 20]]}],
                    "pixels_per_meter": 25,
                    "zebra_speed_threshold_kmh": 15,
                    "approach_deadband_kmh": 2,
                },
            )
            self.assertEqual(response.status_code, 202)
            job = None
            for _ in range(80):
                job = self.client.get(f"/video-analysis/jobs/{job_id}").json()
                if job["status"] == "completed":
                    break
                time.sleep(0.01)
        finally:
            backend_main._analyze_uploaded_video = original_analyzer

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress_percent"], 100.0)
        self.assertEqual(job["result_summary"]["video"]["path"], "study.mp4")
        self.assertIn("annotated_video", job["artifacts"])
        self.assertIn("zebra_metrics", job["result_summary"])
        self.assertIn("zebra_events_csv", job["artifacts"])
        self.assertEqual(self.client.get(job["artifacts"]["zebra_events_csv"]).status_code, 200)
        self.assertEqual(self.client.get(job["artifacts"]["metrics_json"]).status_code, 200)
        self.assertEqual(self.client.get(f"/video-analysis/jobs/{job_id}/artifacts/source").status_code, 404)
        summary = self.client.get("/analytics/summary").json()
        self.assertEqual(summary["total_detections_logged"], 0)
        self.assertEqual(summary["total_crossings_logged"], 0)
        self.assertEqual(summary["total_violations_logged"], 0)

        delete_response = self.client.delete(f"/video-analysis/jobs/{job_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(self.client.get(f"/video-analysis/jobs/{job_id}/preview").status_code, 410)

    def test_video_analysis_line_only_hides_zebra_results_and_artifacts(self):
        job_id = self._upload_analysis_video().json()["job_id"]
        original_analyzer = backend_main._analyze_uploaded_video
        backend_main._analyze_uploaded_video = self._fake_analysis_outputs
        try:
            response = self.client.post(
                f"/video-analysis/jobs/{job_id}/run",
                json={
                    "counting_lines": [{"id": "count_line_1", "points": [[1, 1], [20, 20]]}],
                    "zebra_zones": [],
                    "pixels_per_meter": 25,
                },
            )
            self.assertEqual(response.status_code, 202)
            job = None
            for _ in range(80):
                job = self.client.get(f"/video-analysis/jobs/{job_id}").json()
                if job["status"] == "completed":
                    break
                time.sleep(0.01)
        finally:
            backend_main._analyze_uploaded_video = original_analyzer

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result_summary"]["metrics"]["counts_by_class"], {"car": 1})
        self.assertNotIn("zebra_metrics", job["result_summary"])
        self.assertNotIn("zebra_zones", job["result_summary"])
        self.assertNotIn("zebra_events_csv", job["artifacts"])
        self.assertNotIn("zebra_occupancy_csv", job["artifacts"])
        self.assertEqual(self.client.get(f"/video-analysis/jobs/{job_id}/artifacts/zebra_events_csv").status_code, 404)
        public_summary = self.client.get(job["artifacts"]["summary_json"]).json()
        self.assertNotIn("zebra_metrics", public_summary)
        self.assertNotIn("zebra_zones", public_summary)
        self.assertEqual(self.client.get("/analytics/summary").json()["total_crossings_logged"], 0)

    def test_video_analysis_failure_exposes_diagnostic_without_operational_records(self):
        job_id = self._upload_analysis_video().json()["job_id"]
        original_analyzer = backend_main._analyze_uploaded_video

        def failed_analyzer(_job, _progress_callback):
            raise RuntimeError("Synthetic analyzer failure")

        backend_main._analyze_uploaded_video = failed_analyzer
        try:
            response = self.client.post(
                f"/video-analysis/jobs/{job_id}/run",
                json={
                    "counting_lines": [{"points": [[1, 1], [20, 20]]}],
                    "zebra_zones": [{"points": [[2, 2], [30, 2], [30, 20], [2, 20]]}],
                },
            )
            self.assertEqual(response.status_code, 202)
            job = None
            for _ in range(80):
                job = self.client.get(f"/video-analysis/jobs/{job_id}").json()
                if job["status"] == "failed":
                    break
                time.sleep(0.01)
        finally:
            backend_main._analyze_uploaded_video = original_analyzer

        self.assertEqual(job["status"], "failed")
        self.assertIn("Synthetic analyzer failure", job["failure_message"])
        self.assertEqual(self.client.get("/analytics/summary").json()["total_detections_logged"], 0)

    def test_video_analysis_cleanup_expires_temporary_source(self):
        job = self._upload_analysis_video().json()
        with SessionLocal() as db:
            row = db.query(DBVideoAnalysisJob).filter(DBVideoAnalysisJob.job_id == job["job_id"]).first()
            row.expires_at = datetime.utcnow() - timedelta(seconds=1)
            artifact_dir = Path(row.artifact_dir)
            db.commit()
        response = self.client.get("/video-analysis/jobs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["jobs"], [])
        self.assertFalse(artifact_dir.exists())
        self.assertEqual(self.client.get(f"/video-analysis/jobs/{job['job_id']}").status_code, 410)

    def test_camera_config_endpoint_returns_defaults_and_merged_profiles(self):
        response = self.client.get("/cameras/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("defaults", data)
        self.assertIn("cameras", data)
        self.assertIn("total", data)
        self.assertIn("has_more", data)
        self.assertGreaterEqual(len(data["cameras"]), 1)
        sample_camera = next(camera for camera in data["cameras"] if camera["id"] == "sample_video_01")
        self.assertIn("speed_limit_kmh", sample_camera)
        self.assertNotIn("max_motorcycle_riders", sample_camera)
        self.assertNotIn("rider_association_window_seconds", sample_camera)
        self.assertIn("zones", sample_camera)
        self.assertIn("counting_lines", sample_camera)

    def test_camera_registry_supports_bounded_search_and_pagination(self):
        cameras = [
            {"id": f"fleet_cam_{index:05d}", "location": f"Corridor {index:05d}"}
            for index in range(125)
        ]
        with SessionLocal() as db:
            for camera in cameras:
                backend_main._upsert_camera_profile(db, camera, source="test_fixture")
            db.commit()

        first_page = self.client.get("/cameras/config?q=fleet_cam&limit=20&offset=0").json()
        second_page = self.client.get("/cameras/config?q=fleet_cam&limit=20&offset=20").json()
        location_match = self.client.get("/cameras/config?q=Corridor%2000124&limit=20").json()
        detail = self.client.get("/cameras/config/fleet_cam_00124")

        self.assertEqual(first_page["total"], 125)
        self.assertEqual(len(first_page["cameras"]), 20)
        self.assertTrue(first_page["has_more"])
        self.assertEqual(second_page["cameras"][0]["id"], "fleet_cam_00020")
        self.assertEqual(location_match["cameras"][0]["id"], "fleet_cam_00124")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["location"], "Corridor 00124")

    def test_setup_preview_frame_supports_local_image_source(self):
        image_path = Path(self.config_tmp.name) / "preview.png"
        image = np.zeros((80, 120, 3), dtype=np.uint8)
        image[:, :] = (12, 34, 56)
        cv2.imwrite(str(image_path), image)

        response = self.client.post("/setup/preview-frame", json={
            "camera_id": "setup_cam",
            "source": str(image_path),
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["camera_id"], "setup_cam")
        self.assertEqual(data["width"], 120)
        self.assertEqual(data["height"], 80)

        image_response = self.client.get(data["preview_url"])
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/jpeg")

    def test_setup_camera_config_saves_counting_lines_and_zebra_zone(self):
        response = self.client.post("/setup/camera-config", json={
            "camera_id": "demo_setup_cam",
            "source": "data/sample.mp4",
            "location": "demo_intersection",
            "target_fps": 12,
            "pixels_per_meter": 18.5,
            "speed_limit_kmh": 35.0,
            "counting_lines": [
                {
                    "id": "approach_flow",
                    "label": "Approach Flow",
                    "points": [[100, 10], [100, 400]],
                }
            ],
            "zebra_zones": [
                {
                    "id": "main_zebra",
                    "label": "Main Zebra",
                    "points": [[120, 100], [220, 100], [220, 180], [120, 180]],
                }
            ],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["camera"]["id"], "demo_setup_cam")
        self.assertEqual(len(data["camera"]["counting_lines"]), 1)
        self.assertEqual(len(data["camera"]["zones"]), 1)
        self.assertEqual(data["camera"]["zones"][0]["category"], "zebra_crossing")

        config_response = self.client.get("/cameras/config")
        self.assertEqual(config_response.status_code, 200)
        cameras = config_response.json()["cameras"]
        saved = next(camera for camera in cameras if camera["id"] == "demo_setup_cam")
        self.assertEqual(saved["url"], "data/sample.mp4")
        self.assertEqual(saved["counting_lines"][0]["id"], "approach_flow")
        self.assertEqual(saved["zones"][0]["id"], "main_zebra")

    def test_live_camera_snapshot_endpoints(self):
        camera_dir = Path(self.live_preview_tmp.name) / "sample_video_01"
        camera_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = camera_dir / "latest.jpg"
        snapshot_path.write_bytes(b"\xff\xd8\xff\xd9")
        self.client.post("/detections", json={
            "camera_id": "sample_video_01",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })

        response = self.client.get("/live/cameras")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        sample_status = next(item for item in data["cameras"] if item["camera_id"] == "sample_video_01")
        self.assertTrue(sample_status["snapshot_available"])
        self.assertEqual(sample_status["snapshot_url"], "/live/cameras/sample_video_01/snapshot")
        self.assertIn("health", sample_status)
        self.assertIn("last_detection_at", sample_status)
        self.assertIn("snapshot_age_seconds", sample_status)

        detail_response = self.client.get("/live/cameras/sample_video_01")
        self.assertEqual(detail_response.status_code, 200)
        self.assertTrue(detail_response.json()["snapshot_available"])

        image_response = self.client.get("/live/cameras/sample_video_01/snapshot")
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/jpeg")

    def test_live_camera_snapshot_missing_returns_404(self):
        response = self.client.get("/live/cameras/missing_cam/snapshot")
        self.assertEqual(response.status_code, 404)

    def test_create_detection(self):
        payload = {
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 99,
            "class": "motorcycle",
            "helmet_status": "no_helmet",
            "bbox": [10.5, 20.0, 30.5, 40.0],
            "confidence": 0.95,
            "frame_number": 1,
            "source": "rtsp"
        }
        response = self.client.post("/detections", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"message": "Detection stored"})

    def test_create_speed(self):
        payload = {
            "camera_id": "test_cam",
            "object_id": 99,
            "speed_kmh": 65.4,
            "timestamp": "2023-10-27T10:00:01Z"
        }
        response = self.client.post("/speeds", json=payload)
        self.assertEqual(response.status_code, 201)

    def test_create_violation(self):
        payload = {
            "violation_type": "helmet_violation",
            "object_id": 99,
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        }
        response = self.client.post("/violations", json=payload)
        self.assertEqual(response.status_code, 201)

    def test_retired_multiple_riders_violation_is_rejected(self):
        response = self.client.post("/violations", json={
            "violation_type": "multiple_riders_violation",
            "object_id": 99,
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.assertEqual(response.status_code, 410)

    def test_retired_multiple_riders_records_are_hidden_from_operational_views(self):
        with SessionLocal() as db:
            db.add(DBViolation(
                violation_type="multiple_riders_violation",
                object_id=1,
                camera_id="history_cam",
                timestamp=datetime.fromisoformat("2023-10-27T10:00:01+00:00"),
            ))
            db.add(DBViolation(
                violation_type="speed_violation",
                object_id=2,
                camera_id="history_cam",
                timestamp=datetime.fromisoformat("2023-10-27T10:00:02+00:00"),
            ))
            db.commit()

        summary = self.client.get("/analytics/summary?camera_id=history_cam").json()
        breakdown = self.client.get("/analytics/violations?camera_id=history_cam").json()
        log = self.client.get("/violations/log?camera_id=history_cam").json()

        self.assertEqual(summary["total_violations_logged"], 1)
        self.assertEqual(breakdown["violations"], [{"violation_type": "speed_violation", "count": 1}])
        self.assertEqual(log["total"], 1)
        self.assertEqual(log["items"][0]["violation_type"], "speed_violation")

    def test_create_crossing(self):
        payload = {
            "camera_id": "test_cam",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 99,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:02Z",
            "frame_number": 9,
            "source": "edge",
        }
        response = self.client.post("/crossings", json=payload)
        self.assertEqual(response.status_code, 201)

    def test_violation_evidence_is_captured_and_served(self):
        camera_dir = Path(self.live_clip_tmp.name) / "test_cam"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.mp4").write_bytes(b"fake-mp4-data")

        response = self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 99,
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.assertEqual(response.status_code, 201)

        recent_response = self.client.get("/events/recent?camera_id=test_cam")
        self.assertEqual(recent_response.status_code, 200)
        recent_data = recent_response.json()
        self.assertEqual(len(recent_data["violations"]), 1)
        evidence_url = recent_data["violations"][0]["evidence_url"]
        self.assertTrue(evidence_url)

        evidence_response = self.client.get(evidence_url)
        self.assertEqual(evidence_response.status_code, 200)
        self.assertEqual(evidence_response.headers["content-type"], "video/mp4")

    def test_violation_log_returns_evidence_url_when_available(self):
        camera_dir = Path(self.live_clip_tmp.name) / "cam_recent"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.mp4").write_bytes(b"fake-mp4-data")
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:02Z",
        })

        response = self.client.get("/violations/log?camera_id=cam_recent")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertTrue(data["items"][0]["evidence_url"])
        self.assertEqual(data["items"][0]["evidence_media_type"], "video/mp4")

    def test_violation_evidence_is_disabled_when_capture_flag_is_false(self):
        backend_main._EVIDENCE_CAPTURE_ENABLED = False
        camera_dir = Path(self.live_preview_tmp.name) / "no_evidence_cam"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        response = self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 3,
            "camera_id": "no_evidence_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.assertEqual(response.status_code, 201)

        recent_response = self.client.get("/events/recent?camera_id=no_evidence_cam")
        self.assertEqual(recent_response.status_code, 200)
        recent_data = recent_response.json()
        self.assertEqual(len(recent_data["violations"]), 1)
        self.assertIsNone(recent_data["violations"][0]["evidence_url"])

    def test_violation_detail_returns_related_context(self):
        camera_dir = Path(self.live_clip_tmp.name) / "detail_cam"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.mp4").write_bytes(b"fake-mp4-data")

        self.client.post("/detections", json={
            "camera_id": "detail_cam",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 14,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [10.0, 20.0, 30.0, 40.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "detail_cam",
            "object_id": 14,
            "speed_kmh": 42.0,
            "timestamp": "2023-10-27T10:00:01Z",
            "source": "edge",
        })
        self.client.post("/crossings", json={
            "camera_id": "detail_cam",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 14,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:02Z",
            "source": "edge",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 14,
            "camera_id": "detail_cam",
            "timestamp": "2023-10-27T10:00:03Z",
        })

        log_response = self.client.get("/violations/log?camera_id=detail_cam")
        violation_id = log_response.json()["items"][0]["id"]
        detail_response = self.client.get(f"/violations/detail/{violation_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["id"], violation_id)
        self.assertEqual(detail["camera_id"], "detail_cam")
        self.assertEqual(detail["object_id"], 14)
        self.assertTrue(detail["evidence_url"])
        self.assertEqual(detail["evidence_media_type"], "video/mp4")
        self.assertEqual(len(detail["related"]["detections"]), 1)
        self.assertEqual(len(detail["related"]["speeds"]), 1)
        self.assertEqual(len(detail["related"]["crossings"]), 1)
        self.assertEqual(detail["review_status"], "needs_review")

    def test_violation_review_update_persists_status_and_notes(self):
        camera_dir = Path(self.live_clip_tmp.name) / "review_cam"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.mp4").write_bytes(b"fake-mp4-data")

        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 31,
            "camera_id": "review_cam",
            "timestamp": "2023-10-27T10:00:03Z",
        })

        log_response = self.client.get("/violations/log?camera_id=review_cam")
        violation_id = log_response.json()["items"][0]["id"]
        response = self.client.patch(
            f"/violations/detail/{violation_id}/review",
            json={"review_status": "false_positive", "review_notes": "Occlusion near the crossing line."},
        )
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["review_status"], "false_positive")
        self.assertEqual(detail["review_notes"], "Occlusion near the crossing line.")
        self.assertIsNotNone(detail["reviewed_at"])

        log_after = self.client.get("/violations/log?camera_id=review_cam")
        self.assertEqual(log_after.status_code, 200)
        self.assertEqual(log_after.json()["items"][0]["review_status"], "false_positive")

    def test_violation_review_update_rejects_invalid_status(self):
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 41,
            "camera_id": "review_cam",
            "timestamp": "2023-10-27T10:00:03Z",
        })
        log_response = self.client.get("/violations/log?camera_id=review_cam")
        violation_id = log_response.json()["items"][0]["id"]
        response = self.client.patch(
            f"/violations/detail/{violation_id}/review",
            json={"review_status": "bad_status", "review_notes": ""},
        )
        self.assertEqual(response.status_code, 400)

    def test_analytics_by_camera(self):
        self.client.post("/detections", json={
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_a",
            "object_id": 1,
            "speed_kmh": 40.0,
            "timestamp": "2023-10-27T10:00:01Z",
            "source": "edge",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_b",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.client.post("/crossings", json={
            "camera_id": "cam_a",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 1,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:03Z",
            "source": "edge",
        })

        response = self.client.get("/analytics/by-camera")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        cameras = {item["camera_id"]: item for item in data["cameras"]}
        self.assertEqual(cameras["cam_a"]["detections"], 1)
        self.assertEqual(cameras["cam_a"]["speeds"], 1)
        self.assertEqual(cameras["cam_a"]["violations"], 0)
        self.assertEqual(cameras["cam_a"]["crossings"], 1)
        self.assertEqual(cameras["cam_b"]["violations"], 1)

    def test_detection_analytics_breaks_down_classes(self):
        self.client.post("/detections", json={
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/detections", json={
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:01Z",
            "object_id": 2,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/detections", json={
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:02Z",
            "object_id": 3,
            "class": "pedestrian",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })

        response = self.client.get("/analytics/detections?camera_id=cam_a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_detections"], 3)
        self.assertEqual(data["classes"], [
            {"class": "car", "count": 2},
            {"class": "pedestrian", "count": 1},
        ])
        self.assertEqual(data["cameras"], [{
            "camera_id": "cam_a",
            "total_detections": 3,
            "classes": [
                {"class": "car", "count": 2},
                {"class": "pedestrian", "count": 1},
            ],
        }])

    def test_crossing_analytics(self):
        self.client.post("/crossings", json={
            "camera_id": "cam_a",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 1,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:02Z",
            "source": "edge",
        })
        self.client.post("/crossings", json={
            "camera_id": "cam_a",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 2,
            "class": "pedestrian",
            "direction": "b_to_a",
            "timestamp": "2023-10-27T10:00:03Z",
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_a",
            "object_id": 1,
            "speed_kmh": 42.0,
            "timestamp": "2023-10-27T10:00:02Z",
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_a",
            "object_id": 2,
            "speed_kmh": 5.0,
            "timestamp": "2023-10-27T10:00:03Z",
            "source": "edge",
        })

        response = self.client.get("/analytics/crossings?camera_id=cam_a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_crossings"], 2)
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["lines"][0]["line_id"], "main_gate")
        self.assertEqual(data["counts_by_class"], {"car": 1, "pedestrian": 1})
        self.assertEqual(data["counts_by_direction"], {"a_to_b": 1, "b_to_a": 1})
        self.assertEqual(data["counts_by_line"], {"main_gate": 2})
        self.assertGreaterEqual(data["flow_rate_per_minute"], 0.0)
        self.assertEqual(data["speed_metrics_by_class"]["car"]["avg_speed_kmh"], 42.0)
        self.assertEqual(data["speed_metrics_by_class"]["pedestrian"]["avg_speed_kmh"], 5.0)

    def test_live_dashboard_stream_returns_snapshot(self):
        self.client.post("/detections", json={
            "camera_id": "cam_live",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/crossings", json={
            "camera_id": "cam_live",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 1,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:03Z",
            "source": "edge",
        })

        with self.client.stream("GET", "/live/dashboard?camera_id=cam_live&detail_camera_id=cam_live&once=true") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
            payload = None
            for chunk in response.iter_text():
                if "data: " not in chunk:
                    continue
                for line in chunk.splitlines():
                    if line.startswith("data: "):
                        payload = json.loads(line[6:])
                        break
                if payload is not None:
                    break

        self.assertIsNotNone(payload)
        self.assertIn("summary", payload)
        self.assertIn("crossings", payload)
        self.assertIn("stream", payload)
        self.assertTrue(payload["camera_configs"]["bounded"])
        self.assertEqual(payload["summary"]["camera_id"], "cam_live")
        self.assertEqual(payload["crossings"]["counts_by_line"]["main_gate"], 1)
        self.assertEqual(payload["camera_detail"]["camera_id"], "cam_live")

    def test_live_dashboard_snapshot_bounds_camera_configuration_payload(self):
        with SessionLocal() as db:
            for index in range(40):
                backend_main._upsert_camera_profile(
                    db, {"id": f"bounded_cam_{index:03d}"}, source="test_fixture"
                )
            db.commit()

        with self.client.stream("GET", "/live/dashboard?once=true") as response:
            self.assertEqual(response.status_code, 200)
            payload = None
            for chunk in response.iter_text():
                for line in chunk.splitlines():
                    if line.startswith("data: "):
                        payload = json.loads(line[6:])
                        break
                if payload is not None:
                    break

        self.assertIsNotNone(payload)
        self.assertGreaterEqual(payload["camera_configs"]["total"], 40)
        self.assertLessEqual(len(payload["camera_configs"]["cameras"]), 24)

    def test_analytics_violation_breakdown(self):
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.client.post("/violations", json={
            "violation_type": "helmet_violation",
            "object_id": 2,
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:03Z",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 3,
            "camera_id": "cam_b",
            "timestamp": "2023-10-27T10:00:04Z",
        })

        response = self.client.get("/analytics/violations?camera_id=cam_a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        violations = {item["violation_type"]: item["count"] for item in data["violations"]}
        self.assertEqual(violations["speed_violation"], 1)
        self.assertEqual(violations["helmet_violation"], 1)

    def test_export_safety_events_csv(self):
        camera_dir = Path(self.live_preview_tmp.name) / "cam_export"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 11,
            "camera_id": "cam_export",
            "timestamp": "2023-10-27T10:00:02Z",
        })

        response = self.client.get("/exports/safety-events.csv?camera_id=cam_export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("attachment; filename=", response.headers["content-disposition"])
        self.assertIn("violation_type", response.text)
        self.assertIn("speed_violation", response.text)
        self.assertIn("cam_export", response.text)

    def test_export_crossings_csv(self):
        self.client.post("/crossings", json={
            "camera_id": "cam_cross",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 21,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:02Z",
            "frame_number": 9,
            "source": "edge",
        })

        response = self.client.get("/exports/crossings.csv?camera_id=cam_cross")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("line_label", response.text)
        self.assertIn("Main Gate", response.text)
        self.assertIn("a_to_b", response.text)

    def test_export_traffic_flow_json(self):
        self.client.post("/crossings", json={
            "camera_id": "cam_flow",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 1,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:02Z",
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_flow",
            "object_id": 1,
            "speed_kmh": 42.0,
            "timestamp": "2023-10-27T10:00:02Z",
            "source": "edge",
        })

        response = self.client.get("/exports/traffic-flow.json?camera_id=cam_flow")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "application/json")
        data = response.json()
        self.assertEqual(data["scope"]["camera_id"], "cam_flow")
        self.assertIn("summary", data)
        self.assertIn("crossings", data)
        self.assertIn("speed_distribution", data)
        self.assertEqual(data["crossings"]["counts_by_line"]["main_gate"], 1)

    def test_recent_events(self):
        self.client.post("/detections", json={
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_recent",
            "object_id": 1,
            "speed_kmh": 44.0,
            "timestamp": "2023-10-27T10:00:01Z",
            "source": "edge",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.client.post("/crossings", json={
            "camera_id": "cam_recent",
            "line_id": "main_gate",
            "line_label": "Main Gate",
            "object_id": 1,
            "class": "car",
            "direction": "a_to_b",
            "timestamp": "2023-10-27T10:00:03Z",
            "source": "edge",
        })

        response = self.client.get("/events/recent?camera_id=cam_recent&limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["detections"]), 1)
        self.assertEqual(len(data["speeds"]), 1)
        self.assertEqual(len(data["violations"]), 1)
        self.assertEqual(len(data["crossings"]), 1)
        self.assertEqual(data["detections"][0]["class"], "car")

    def test_recent_events_support_time_filters(self):
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T09:00:02Z",
        })
        self.client.post("/violations", json={
            "violation_type": "helmet_violation",
            "object_id": 2,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T11:00:02Z",
        })

        response = self.client.get(
            "/events/recent?camera_id=cam_recent&start=2023-10-27T10:00:00Z&end=2023-10-27T12:00:00Z"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["violations"]), 1)
        self.assertEqual(data["violations"][0]["violation_type"], "helmet_violation")

    def test_summary_filters(self):
        self.client.post("/detections", json={
            "camera_id": "cam_filter",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/detections", json={
            "camera_id": "cam_filter",
            "timestamp": "2023-10-27T11:00:00Z",
            "object_id": 2,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })

        response = self.client.get(
            "/analytics/summary?camera_id=cam_filter&start=2023-10-27T10:30:00Z&end=2023-10-27T11:30:00Z"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_detections_logged"], 1)
        self.assertEqual(data["camera_id"], "cam_filter")
        self.assertEqual(data["detection_classes"], [{"class": "car", "count": 1}])

    def test_z_analytics_summary(self):
        self.client.post("/detections", json={
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 99,
            "class": "motorcycle",
            "helmet_status": "no_helmet",
            "bbox": [10.5, 20.0, 30.5, 40.0],
            "confidence": 0.95,
            "frame_number": 1,
            "source": "rtsp"
        })
        response = self.client.get("/analytics/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_detections_logged", data)
        self.assertEqual(data["total_detections_logged"], 1)
        self.assertEqual(data["detection_classes"], [{"class": "motorcycle", "count": 1}])
        self.assertEqual(data["total_speeds_logged"], 0)
        self.assertEqual(data["total_crossings_logged"], 0)
        self.assertIn("total_speeds_logged", data)

    # ------------------------------------------------------------------
    # Trend analysis (week-over-week / month-over-month + anomaly flags)
    # ------------------------------------------------------------------

    def _post_detection(self, camera_id, timestamp, object_id):
        response = self.client.post("/detections", json={
            "camera_id": camera_id,
            "timestamp": timestamp,
            "object_id": object_id,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.assertEqual(response.status_code, 201)

    def test_trends_wow_delta(self):
        for i in range(5):
            self._post_detection("cam_trend_wow", "2024-01-10T10:00:00Z", 100 + i)
        for i in range(3):
            self._post_detection("cam_trend_wow", "2024-01-05T10:00:00Z", 200 + i)

        response = self.client.get(
            "/analytics/trends/summary"
            "?period=week&camera_id=cam_trend_wow&reference_date=2024-01-15T00:00:00Z&baseline_periods=1"
        )
        self.assertEqual(response.status_code, 200)
        metric = response.json()["metrics"]["total_detections_logged"]
        self.assertEqual(metric["current"], 5)
        self.assertEqual(metric["previous"], 3)
        self.assertEqual(metric["delta"], 2)
        self.assertAlmostEqual(metric["delta_pct"], 66.67, places=2)

    def test_trends_mom_delta(self):
        for i in range(4):
            self._post_detection("cam_trend_mom", "2024-02-05T10:00:00Z", 300 + i)
        for i in range(2):
            self._post_detection("cam_trend_mom", "2024-01-10T10:00:00Z", 400 + i)

        response = self.client.get(
            "/analytics/trends/summary"
            "?period=month&camera_id=cam_trend_mom&reference_date=2024-02-15T00:00:00Z&baseline_periods=1"
        )
        self.assertEqual(response.status_code, 200)
        metric = response.json()["metrics"]["total_detections_logged"]
        self.assertEqual(metric["current"], 4)
        self.assertEqual(metric["previous"], 2)
        self.assertEqual(metric["delta"], 2)
        self.assertAlmostEqual(metric["delta_pct"], 100.0, places=2)

    def test_trends_anomaly_flagging(self):
        # Oldest -> newest baseline windows for reference_date=2024-03-15, period=week, baseline_periods=6.
        baseline_windows = [
            ("2024-01-22T10:00:00Z", 3),
            ("2024-01-29T10:00:00Z", 4),
            ("2024-02-05T10:00:00Z", 5),
            ("2024-02-12T10:00:00Z", 4),
            ("2024-02-19T10:00:00Z", 3),
            ("2024-02-26T10:00:00Z", 5),
        ]

        for camera_id, current_count in (("cam_anomaly_spike", 40), ("cam_anomaly_normal", 5)):
            object_id = 0
            for timestamp, count in baseline_windows:
                for _ in range(count):
                    object_id += 1
                    self._post_detection(camera_id, timestamp, object_id)
            for _ in range(current_count):
                object_id += 1
                self._post_detection(camera_id, "2024-03-10T10:00:00Z", object_id)

        spike_response = self.client.get(
            "/analytics/trends/summary"
            "?period=week&camera_id=cam_anomaly_spike&reference_date=2024-03-15T00:00:00Z&baseline_periods=6"
        )
        self.assertEqual(spike_response.status_code, 200)
        spike_metric = spike_response.json()["metrics"]["total_detections_logged"]
        self.assertEqual(spike_metric["baseline_sample_size"], 6)
        self.assertAlmostEqual(spike_metric["baseline_mean"], 4.0, places=2)
        self.assertGreater(abs(spike_metric["z_score"]), 2.0)
        self.assertTrue(spike_metric["is_anomaly"])

        normal_response = self.client.get(
            "/analytics/trends/summary"
            "?period=week&camera_id=cam_anomaly_normal&reference_date=2024-03-15T00:00:00Z&baseline_periods=6"
        )
        self.assertEqual(normal_response.status_code, 200)
        normal_metric = normal_response.json()["metrics"]["total_detections_logged"]
        self.assertLessEqual(abs(normal_metric["z_score"]), 2.0)
        self.assertFalse(normal_metric["is_anomaly"])

    def test_trends_insufficient_baseline(self):
        for i in range(5):
            self._post_detection("cam_trend_fresh", "2024-04-10T10:00:00Z", 500 + i)

        response = self.client.get(
            "/analytics/trends/summary"
            "?period=week&camera_id=cam_trend_fresh&reference_date=2024-04-15T00:00:00Z&baseline_periods=1"
        )
        self.assertEqual(response.status_code, 200)
        metric = response.json()["metrics"]["total_detections_logged"]
        self.assertEqual(metric["current"], 5)
        self.assertEqual(metric["previous"], 0)
        self.assertEqual(metric["baseline_sample_size"], 1)
        self.assertIsNone(metric["baseline_mean"])
        self.assertIsNone(metric["baseline_stddev"])
        self.assertIsNone(metric["z_score"])
        self.assertFalse(metric["is_anomaly"])

    def test_trends_camera_filter(self):
        for i in range(5):
            self._post_detection("cam_trend_filter_x", "2024-05-10T10:00:00Z", 600 + i)
        for i in range(2):
            self._post_detection("cam_trend_filter_y", "2024-05-10T10:00:00Z", 700 + i)

        response = self.client.get(
            "/analytics/trends/summary"
            "?period=week&camera_id=cam_trend_filter_x&reference_date=2024-05-15T00:00:00Z&baseline_periods=1"
        )
        self.assertEqual(response.status_code, 200)
        metric = response.json()["metrics"]["total_detections_logged"]
        self.assertEqual(metric["current"], 5)

    def test_trends_invalid_period_param(self):
        response = self.client.get("/analytics/trends/summary?period=quarter")
        self.assertEqual(response.status_code, 422)

    def test_trends_metric_endpoint_returns_history(self):
        for i in range(5):
            self._post_detection("cam_trend_history", "2024-01-10T10:00:00Z", 800 + i)

        response = self.client.get(
            "/analytics/trends/detections"
            "?period=week&camera_id=cam_trend_history&reference_date=2024-01-15T00:00:00Z&baseline_periods=1"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current"], 5)
        self.assertIn("history", data)
        self.assertEqual(data["history"][-1]["value"], 5)


if __name__ == '__main__':
    unittest.main()
