import argparse
import logging
import os
import cv2
import time
from datetime import datetime, timezone
from camera_capture import CameraCapture
from detection import EdgeDetector
from line_counter import LineCrossingCounter
from live_preview import LivePreviewWriter, RollingEvidenceClipWriter
from publisher import MQTTPublisher
from common.camera_config import build_camera_profile_map

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EdgeVisionMain")


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def main():
    parser = argparse.ArgumentParser(description="Edge Vision Agent")
    parser.add_argument(
        "--source",
        type=str,
        default=os.getenv("EDGE_SOURCE", "0"),
        help="Camera source (index or file path)",
    )
    parser.add_argument(
        "--camera-id",
        type=str,
        default=os.getenv("CAMERA_ID", "edge_cam_01"),
        help="Camera ID",
    )
    parser.add_argument(
        "--broker",
        type=str,
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="MQTT broker host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        default=_env_flag("EDGE_SHOW_VIDEO", False),
        help="Show video feed",
    )
    parser.add_argument(
        "--live-preview-dir",
        type=str,
        default=os.getenv("LIVE_PREVIEW_DIR", "artifacts/live_frames"),
        help="Directory used to publish latest annotated camera snapshots for the dashboard",
    )
    parser.add_argument(
        "--live-preview-interval",
        type=float,
        default=float(os.getenv("LIVE_PREVIEW_INTERVAL_SECONDS", "1.0")),
        help="Seconds between live preview snapshot writes",
    )
    parser.add_argument(
        "--camera-config",
        type=str,
        default=os.getenv("CAMERA_CONFIG_PATH", "config/cameras.yaml"),
        help="Camera configuration file with calibration, zones, and counting lines",
    )
    parser.add_argument(
        "--live-clip-dir",
        type=str,
        default=os.getenv("LIVE_CLIP_DIR", "artifacts/live_clips"),
        help="Directory used to publish the latest short annotated evidence clips for each camera",
    )
    parser.add_argument(
        "--live-clip-duration",
        type=float,
        default=float(os.getenv("LIVE_CLIP_DURATION_SECONDS", "4.0")),
        help="Duration in seconds for rolling evidence clips",
    )
    parser.add_argument(
        "--live-clip-interval",
        type=float,
        default=float(os.getenv("LIVE_CLIP_INTERVAL_SECONDS", "1.0")),
        help="Seconds between rolling evidence clip updates",
    )
    args = parser.parse_args()

    # Initialize components
    camera_profiles = build_camera_profile_map(args.camera_config)
    camera_profile = camera_profiles.get(args.camera_id, {})
    capture = CameraCapture(args.source)
    detector = EdgeDetector()
    publisher = MQTTPublisher(broker_host=args.broker, broker_port=args.port)
    line_counter = LineCrossingCounter(camera_profile.get("counting_lines"))
    preview_writer = LivePreviewWriter(
        base_dir=args.live_preview_dir,
        interval_seconds=args.live_preview_interval,
        enabled=True,
    )
    clip_writer = RollingEvidenceClipWriter(
        base_dir=args.live_clip_dir,
        clip_duration_seconds=args.live_clip_duration,
        write_interval_seconds=args.live_clip_interval,
        enabled=True,
        fps=float(camera_profile.get("target_fps") or 10.0),
    )

    if not capture.connect():
        logger.error("Exiting due to capture failure.")
        return

    # In a real edge scenario, if MQTT is down we might buffer, but for MVP we just connect
    publisher.connect()

    logger.info("Starting edge vision pipeline...")
    try:
        while True:
            start_time = time.time()
            frame, frame_number = capture.read_frame()
            
            if frame is None:
                break
                
            results, annotated_frame, counts = detector.detect_and_track(frame)
            published = publisher.publish_detections(args.camera_id, frame_number, results)
            crossings = line_counter.process_tracks(
                camera_id=args.camera_id,
                frame_number=frame_number,
                tracks=[
                    {
                        "object_id": int(box_id),
                        "class_name": ("pedestrian" if results.names[cls_id] == "person" else results.names[cls_id]),
                        "bbox": [float(c) for c in box],
                    }
                    for box, box_id, cls_id in zip(
                        results.boxes.xyxy.cpu().numpy() if results.boxes is not None and results.boxes.id is not None else [],
                        results.boxes.id.int().cpu().numpy() if results.boxes is not None and results.boxes.id is not None else [],
                        results.boxes.cls.int().cpu().numpy() if results.boxes is not None and results.boxes.id is not None else [],
                    )
                ],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            published_crossings = publisher.publish_crossings(crossings)
            preview_writer.write_frame(args.camera_id, annotated_frame)
            clip_writer.add_frame(args.camera_id, annotated_frame, fps=float(camera_profile.get("target_fps") or 10.0))
            
            fps = 1.0 / (time.time() - start_time)
            if frame_number % 30 == 0:
                 logger.info(
                     f"Frame {frame_number}: Published {published} detections and {published_crossings} crossings. "
                     f"FPS: {fps:.1f}. Counts: {counts}"
                 )

            if args.show:
                # Resize for display if too large
                height, width = annotated_frame.shape[:2]
                if width > 1280:
                     annotated_frame = cv2.resize(annotated_frame, (1280, int(height * (1280/width))))
                cv2.imshow("Edge Vision with Counter", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        capture.release()
        publisher.disconnect()
        cv2.destroyAllWindows()
        logger.info("Pipeline stopped.")

if __name__ == "__main__":
    main()
