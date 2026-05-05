import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np
import yaml

from common.camera_config import build_camera_profile_map
from speed_estimation.calibration import CameraCalibration
from speed_estimation.speed_calc import SpeedCalculator


VEHICLE_CLASSES = {"car", "bus", "truck", "motorcycle"}
PEDESTRIAN_CLASSES = {"pedestrian"}


@dataclass
class CalibrationConfig:
    camera_id: str
    pixels_per_meter: float
    source: str
    reference_segments: List[dict]
    approach_speed_threshold_kmh: float
    pedestrian_speed_threshold_kmh: float
    interaction_window_seconds: float
    approach_distance_m: float
    pedestrian_near_distance_m: float
    zebra_zones: List[dict]


@dataclass
class TrackObservation:
    object_id: int
    class_name: str
    bbox: List[float]
    confidence: float


def _point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    if len(point) != 2 or len(polygon) < 3:
        return False

    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _bbox_bottom_center(bbox: List[float]) -> Tuple[float, float]:
    x1, _, x2, y2 = bbox
    return ((float(x1) + float(x2)) / 2.0, float(y2))


def _distance(point_a: Tuple[float, float], point_b: Tuple[float, float]) -> float:
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _polygon_centroid(points: List[List[float]]) -> Tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    return (
        sum(float(point[0]) for point in points) / len(points),
        sum(float(point[1]) for point in points) / len(points),
    )


def _point_segment_distance(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    denom = (dx * dx) + (dy * dy)
    if denom <= 1e-9:
        return _distance(point, start)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / denom))
    closest = (sx + (t * dx), sy + (t * dy))
    return _distance(point, closest)


def _point_polygon_distance(point: Tuple[float, float], polygon: List[List[float]]) -> float:
    if _point_in_polygon(point, polygon):
        return 0.0
    if not polygon:
        return float("inf")
    distances = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        distances.append(
            _point_segment_distance(
                point,
                (float(start[0]), float(start[1])),
                (float(end[0]), float(end[1])),
            )
        )
    return min(distances)


def _derive_pixels_per_meter(raw_config: dict) -> Tuple[float, str]:
    meters_per_pixel = raw_config.get("meters_per_pixel")
    if meters_per_pixel:
        return 1.0 / float(meters_per_pixel), "meters_per_pixel"

    pixels_per_meter = raw_config.get("pixels_per_meter")
    if pixels_per_meter:
        return float(pixels_per_meter), "pixels_per_meter"

    for segment in raw_config.get("reference_segments") or []:
        points = segment.get("image_points") or []
        real_distance_m = segment.get("real_distance_m")
        if len(points) != 2 or not real_distance_m:
            continue
        pixel_distance = _distance(
            (float(points[0][0]), float(points[0][1])),
            (float(points[1][0]), float(points[1][1])),
        )
        if pixel_distance > 0:
            return pixel_distance / float(real_distance_m), f"reference_segment:{segment.get('id', 'unnamed')}"

    raise ValueError(
        "Calibration must define pixels_per_meter, meters_per_pixel, or at least one valid reference segment."
    )


def load_calibration(path: str, camera_id: str) -> CalibrationConfig:
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    configured_camera_id = raw.get("camera_id")
    if configured_camera_id and configured_camera_id != camera_id:
        raise ValueError(
            f"Calibration camera_id {configured_camera_id!r} does not match requested camera_id {camera_id!r}."
        )

    pixels_per_meter, source = _derive_pixels_per_meter(raw)
    return CalibrationConfig(
        camera_id=camera_id,
        pixels_per_meter=pixels_per_meter,
        source=source,
        reference_segments=list(raw.get("reference_segments") or []),
        approach_speed_threshold_kmh=float(raw.get("approach_speed_threshold_kmh", 15.0)),
        pedestrian_speed_threshold_kmh=float(raw.get("pedestrian_speed_threshold_kmh", 8.0)),
        interaction_window_seconds=float(raw.get("interaction_window_seconds", 3.0)),
        approach_distance_m=float(raw.get("approach_distance_m", 12.0)),
        pedestrian_near_distance_m=float(raw.get("pedestrian_near_distance_m", 2.0)),
        zebra_zones=_normalize_drawn_zones(raw.get("zebra_zones")),
    )


def _normalize_drawn_zones(zones: Optional[List[dict]]) -> List[dict]:
    normalized = []
    for index, zone in enumerate(zones or []):
        points = []
        for point in zone.get("points", []):
            if (
                isinstance(point, (list, tuple))
                and len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
            ):
                points.append([float(point[0]), float(point[1])])
        if len(points) < 3:
            continue
        zone_id = zone.get("id") or f"drawn_zebra_{index + 1}"
        normalized.append(
            {
                "id": zone_id,
                "label": zone.get("label", zone_id.replace("_", " ").title()),
                "type": zone.get("type", "polygon"),
                "category": "zebra_crossing",
                "points": points,
            }
        )
    return normalized


def _zebra_zones(camera_profile: dict) -> List[dict]:
    return [
        zone for zone in camera_profile.get("zones", [])
        if zone.get("category") == "zebra_crossing" and len(zone.get("points", [])) >= 3
    ]


class YoloTrackDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.25):
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame) -> List[TrackObservation]:
        tracked = self.model.track(
            source=frame,
            conf=self.confidence,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0, 1, 2, 3, 5, 7],
            verbose=False,
        )
        results = tracked[0]
        if results.boxes is None or results.boxes.id is None:
            return []

        names = results.names
        observations = []
        for box, track_id, conf, cls_id in zip(
            results.boxes.xyxy.cpu().numpy(),
            results.boxes.id.int().cpu().numpy(),
            results.boxes.conf.cpu().numpy(),
            results.boxes.cls.int().cpu().numpy(),
        ):
            class_name = names[int(cls_id)]
            if class_name == "person":
                class_name = "pedestrian"
            observations.append(
                TrackObservation(
                    object_id=int(track_id),
                    class_name=class_name,
                    bbox=[float(value) for value in box],
                    confidence=float(conf),
                )
            )
        return observations


class ZebraComplianceAnalyzer:
    def __init__(
        self,
        camera_id: str,
        camera_profile: dict,
        calibration: CalibrationConfig,
        detector=None,
    ):
        self.camera_id = camera_id
        self.camera_profile = camera_profile
        self.calibration = calibration
        self.detector = detector or YoloTrackDetector()
        self.zebra_zones = calibration.zebra_zones or _zebra_zones(camera_profile)
        if not self.zebra_zones:
            raise ValueError(f"No zebra_crossing zone configured for camera_id {camera_id!r}.")

        self.speed_calculator = SpeedCalculator(
            CameraCalibration(pixels_per_meter=calibration.pixels_per_meter),
            history_size=int(camera_profile.get("speed_history_size", 5)),
            max_speed_kmh=float(camera_profile.get("speed_max_kmh", 200.0)),
            min_time_delta_seconds=float(camera_profile.get("speed_min_time_delta_seconds", 0.0)),
            smoothing_alpha=float(camera_profile.get("speed_smoothing_alpha", 1.0)),
            outlier_mode=camera_profile.get("speed_outlier_mode", "cap"),
        )
        self.previous_distances: Dict[Tuple[int, str], float] = {}
        self.recent_pedestrians: Dict[int, dict] = {}
        self.object_summaries: Dict[int, dict] = {}
        self.event_keys = set()
        self.events = []
        self.track_rows = []

    def _observation_zone_state(self, observation: TrackObservation, zone: dict) -> dict:
        point = _bbox_bottom_center(observation.bbox)
        polygon = zone.get("points", [])
        distance_px = _point_polygon_distance(point, polygon)
        distance_m = distance_px / self.calibration.pixels_per_meter
        inside = distance_px == 0.0
        previous_distance = self.previous_distances.get((observation.object_id, zone["id"]))
        moving_toward = previous_distance is not None and distance_px < previous_distance
        self.previous_distances[(observation.object_id, zone["id"])] = distance_px
        return {
            "point": point,
            "inside": inside,
            "distance_m": distance_m,
            "moving_toward": moving_toward,
        }

    def _update_object_summary(self, observation: TrackObservation, speed_kmh: Optional[float]):
        summary = self.object_summaries.setdefault(
            observation.object_id,
            {
                "object_id": observation.object_id,
                "class": observation.class_name,
                "frames_seen": 0,
                "max_speed_kmh": None,
                "avg_speed_kmh": None,
                "_speed_samples": [],
            },
        )
        summary["class"] = observation.class_name
        summary["frames_seen"] += 1
        if speed_kmh is not None:
            summary["_speed_samples"].append(float(speed_kmh))
            summary["max_speed_kmh"] = max(summary["max_speed_kmh"] or 0.0, float(speed_kmh))
            summary["avg_speed_kmh"] = sum(summary["_speed_samples"]) / len(summary["_speed_samples"])

    def _active_pedestrians(self, frame_observations: List[dict], elapsed_seconds: float) -> List[dict]:
        active = []
        near_distance = self.calibration.pedestrian_near_distance_m
        for row in frame_observations:
            if row["class"] not in PEDESTRIAN_CLASSES:
                continue
            if row["inside_zebra"] or row["distance_to_zebra_m"] <= near_distance:
                stored = dict(row)
                stored["_last_seen_seconds"] = elapsed_seconds
                self.recent_pedestrians[row["object_id"]] = stored
                active.append(row)
        for pedestrian in self.recent_pedestrians.values():
            if elapsed_seconds - pedestrian["_last_seen_seconds"] <= self.calibration.interaction_window_seconds:
                if pedestrian["object_id"] not in {row["object_id"] for row in active}:
                    active.append(pedestrian)
        return active

    def _vehicle_status(self, row: dict) -> str:
        if row["inside_zebra"]:
            return "inside_zebra"
        if row["moving_toward_zebra"] and row["distance_to_zebra_m"] <= self.calibration.approach_distance_m:
            return "approaching_zebra"
        return "observed"

    def _maybe_emit_events(self, frame_number: int, elapsed_seconds: float, frame_rows: List[dict]):
        active_pedestrians = self._active_pedestrians(frame_rows, elapsed_seconds)
        if not active_pedestrians:
            return []

        emitted_this_frame = []
        for vehicle in frame_rows:
            if vehicle["class"] not in VEHICLE_CLASSES:
                continue
            speed = vehicle.get("speed_kmh")
            if speed is None or speed < self.calibration.approach_speed_threshold_kmh:
                continue

            vehicle_status = self._vehicle_status(vehicle)
            if vehicle_status == "observed":
                continue

            nearest_pedestrian = min(
                active_pedestrians,
                key=lambda pedestrian: pedestrian["distance_to_zebra_m"],
            )
            event_type = "zebra_crossing_violation" if vehicle["inside_zebra"] else "zebra_yielding_risk"
            key = (
                event_type,
                vehicle["object_id"],
                nearest_pedestrian["object_id"],
                vehicle["zebra_zone_id"],
            )
            if key in self.event_keys:
                continue
            self.event_keys.add(key)

            event = {
                "event_type": event_type,
                "camera_id": self.camera_id,
                "frame_number": frame_number,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "zone_id": vehicle["zebra_zone_id"],
                "vehicle_object_id": vehicle["object_id"],
                "vehicle_class": vehicle["class"],
                "vehicle_speed_kmh": round(float(speed), 2),
                "vehicle_status": vehicle_status,
                "pedestrian_object_id": nearest_pedestrian["object_id"],
                "pedestrian_speed_kmh": (
                    round(float(nearest_pedestrian["speed_kmh"]), 2)
                    if nearest_pedestrian.get("speed_kmh") is not None else None
                ),
                "pedestrian_status": (
                    "inside_zebra" if nearest_pedestrian["inside_zebra"] else "near_zebra"
                ),
            }
            self.events.append(event)
            emitted_this_frame.append(event)
        return emitted_this_frame

    def analyze_frame(self, frame, frame_number: int, elapsed_seconds: float) -> Tuple[List[dict], List[dict]]:
        observations = self.detector.detect(frame)
        frame_rows = []
        timestamp_iso = (
            datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=elapsed_seconds)
        ).isoformat()

        for observation in observations:
            if observation.class_name not in VEHICLE_CLASSES and observation.class_name not in PEDESTRIAN_CLASSES:
                continue

            speed = self.speed_calculator.update_position(
                observation.object_id,
                timestamp_iso,
                observation.bbox,
            )
            self._update_object_summary(observation, speed)

            nearest_zone = None
            nearest_state = None
            for zone in self.zebra_zones:
                state = self._observation_zone_state(observation, zone)
                if nearest_state is None or state["distance_m"] < nearest_state["distance_m"]:
                    nearest_zone = zone
                    nearest_state = state

            row = {
                "frame_number": frame_number,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "camera_id": self.camera_id,
                "object_id": observation.object_id,
                "class": observation.class_name,
                "confidence": round(float(observation.confidence), 4),
                "bbox": json.dumps([round(float(value), 2) for value in observation.bbox]),
                "speed_kmh": round(float(speed), 2) if speed is not None else None,
                "zebra_zone_id": nearest_zone["id"],
                "inside_zebra": nearest_state["inside"],
                "moving_toward_zebra": nearest_state["moving_toward"],
                "distance_to_zebra_m": round(float(nearest_state["distance_m"]), 2),
                "time_to_zebra_seconds": None,
            }
            if (
                speed is not None
                and speed > 0
                and nearest_state["moving_toward"]
                and nearest_state["distance_m"] > 0
            ):
                speed_mps = float(speed) / 3.6
                row["time_to_zebra_seconds"] = round(nearest_state["distance_m"] / speed_mps, 2)
            frame_rows.append(row)
            self.track_rows.append(row)

        return frame_rows, self._maybe_emit_events(frame_number, elapsed_seconds, frame_rows)

    def annotate_frame(self, frame, frame_rows: List[dict], frame_events: List[dict]):
        annotated = frame.copy()
        for zone in self.zebra_zones:
            points = zone.get("points", [])
            polygon = np.array(points, dtype="int32")
            cv2.polylines(annotated, [polygon], isClosed=True, color=(0, 215, 255), thickness=2)
            label_x, label_y = map(int, _polygon_centroid(points))
            cv2.putText(
                annotated,
                zone.get("label", zone["id"]),
                (label_x, max(20, label_y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

        for segment in self.calibration.reference_segments:
            points = segment.get("image_points") or []
            if len(points) == 2:
                start = tuple(int(value) for value in points[0])
                end = tuple(int(value) for value in points[1])
                cv2.line(annotated, start, end, (255, 255, 0), 2)
                cv2.putText(
                    annotated,
                    segment.get("id", "calibration"),
                    (start[0], max(20, start[1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

        for row in frame_rows:
            bbox = json.loads(row["bbox"])
            x1, y1, x2, y2 = [int(value) for value in bbox]
            color = (60, 220, 60) if row["class"] == "pedestrian" else (255, 120, 60)
            if any(event["vehicle_object_id"] == row["object_id"] for event in frame_events):
                color = (0, 0, 255)
            if any(event["pedestrian_object_id"] == row["object_id"] for event in frame_events):
                color = (0, 165, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            speed_label = "--" if row["speed_kmh"] is None else f"{row['speed_kmh']:.1f}km/h"
            status = self._vehicle_status(row) if row["class"] in VEHICLE_CLASSES else (
                "inside_zebra" if row["inside_zebra"] else "near_zebra" if row["distance_to_zebra_m"] <= self.calibration.pedestrian_near_distance_m else "observed"
            )
            cv2.putText(
                annotated,
                f"#{row['object_id']} {row['class']} {speed_label} {status}",
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        if frame_events:
            banner = " | ".join(event["event_type"] for event in frame_events)
            cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 36), (0, 0, 180), -1)
            cv2.putText(
                annotated,
                banner[:100],
                (12, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        return annotated

    def _final_object_summaries(self) -> List[dict]:
        summaries = []
        for summary in self.object_summaries.values():
            clean = {key: value for key, value in summary.items() if not key.startswith("_")}
            if clean["max_speed_kmh"] is not None:
                clean["max_speed_kmh"] = round(float(clean["max_speed_kmh"]), 2)
            if clean["avg_speed_kmh"] is not None:
                clean["avg_speed_kmh"] = round(float(clean["avg_speed_kmh"]), 2)
            summaries.append(clean)
        return sorted(summaries, key=lambda item: item["object_id"])

    def analyze_video(self, video_path: str, output_dir: str) -> dict:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        writer_path = output_path / "annotated.mp4"
        writer = cv2.VideoWriter(
            str(writer_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )

        frame_number = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_number += 1
                elapsed_seconds = (frame_number - 1) / fps
                frame_rows, frame_events = self.analyze_frame(frame, frame_number, elapsed_seconds)
                writer.write(self.annotate_frame(frame, frame_rows, frame_events))
        finally:
            capture.release()
            writer.release()

        self._write_csv(output_path / "events.csv", self.events, event_fieldnames())
        self._write_csv(output_path / "tracks.csv", self.track_rows, track_fieldnames())

        summary_path = output_path / "summary.json"
        summary = {
            "video": {
                "path": str(video_path),
                "fps": fps,
                "width": width,
                "height": height,
                "frame_count": frame_count,
                "processed_frames": frame_number,
            },
            "camera_id": self.camera_id,
            "calibration": {
                "pixels_per_meter": round(self.calibration.pixels_per_meter, 6),
                "source": self.calibration.source,
                "reference_segments": self.calibration.reference_segments,
            },
            "thresholds": {
                "approach_speed_threshold_kmh": self.calibration.approach_speed_threshold_kmh,
                "pedestrian_speed_threshold_kmh": self.calibration.pedestrian_speed_threshold_kmh,
                "interaction_window_seconds": self.calibration.interaction_window_seconds,
                "approach_distance_m": self.calibration.approach_distance_m,
                "pedestrian_near_distance_m": self.calibration.pedestrian_near_distance_m,
            },
            "zebra_zones": self.zebra_zones,
            "aggregate_counts": {
                "objects_seen": len(self.object_summaries),
                "events": len(self.events),
                "zebra_yielding_risk": sum(1 for event in self.events if event["event_type"] == "zebra_yielding_risk"),
                "zebra_crossing_violation": sum(1 for event in self.events if event["event_type"] == "zebra_crossing_violation"),
            },
            "objects": self._final_object_summaries(),
            "events": self.events,
            "outputs": {
                "annotated_video": str(writer_path),
                "events_csv": str(output_path / "events.csv"),
                "tracks_csv": str(output_path / "tracks.csv"),
                "summary_json": str(summary_path),
            },
            "notes": [
                "Speed estimates depend on calibration quality and are approximate.",
                "Compliance v1 flags yielding risk around configured zebra zones; it is not certified enforcement evidence.",
            ],
        }

        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        return summary

    @staticmethod
    def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})


def event_fieldnames() -> List[str]:
    return [
        "event_type",
        "camera_id",
        "frame_number",
        "elapsed_seconds",
        "zone_id",
        "vehicle_object_id",
        "vehicle_class",
        "vehicle_speed_kmh",
        "vehicle_status",
        "pedestrian_object_id",
        "pedestrian_speed_kmh",
        "pedestrian_status",
    ]


def track_fieldnames() -> List[str]:
    return [
        "frame_number",
        "elapsed_seconds",
        "camera_id",
        "object_id",
        "class",
        "confidence",
        "bbox",
        "speed_kmh",
        "zebra_zone_id",
        "inside_zebra",
        "moving_toward_zebra",
        "distance_to_zebra_m",
        "time_to_zebra_seconds",
    ]


def build_drawn_setup_config(
    camera_id: str,
    zebra_points: List[List[float]],
    reference_points: List[List[float]],
    real_distance_m: float,
    zone_id: str = "drawn_zebra_crossing",
    reference_id: str = "drawn_reference_line",
    approach_speed_threshold_kmh: float = 15.0,
    pedestrian_speed_threshold_kmh: float = 8.0,
    interaction_window_seconds: float = 3.0,
    approach_distance_m: float = 12.0,
    pedestrian_near_distance_m: float = 2.0,
) -> dict:
    if len(zebra_points) < 3:
        raise ValueError("Draw at least three points around the zebra crossing area.")
    if len(reference_points) != 2:
        raise ValueError("Draw exactly two points for the calibration reference line.")
    if real_distance_m <= 0:
        raise ValueError("real_distance_m must be greater than zero.")

    return {
        "camera_id": camera_id,
        "meters_per_pixel": None,
        "reference_segments": [
            {
                "id": reference_id,
                "image_points": [
                    [float(reference_points[0][0]), float(reference_points[0][1])],
                    [float(reference_points[1][0]), float(reference_points[1][1])],
                ],
                "real_distance_m": float(real_distance_m),
            }
        ],
        "zebra_zones": [
            {
                "id": zone_id,
                "label": "Drawn Zebra Crossing",
                "type": "polygon",
                "category": "zebra_crossing",
                "points": [[float(point[0]), float(point[1])] for point in zebra_points],
            }
        ],
        "approach_speed_threshold_kmh": float(approach_speed_threshold_kmh),
        "pedestrian_speed_threshold_kmh": float(pedestrian_speed_threshold_kmh),
        "interaction_window_seconds": float(interaction_window_seconds),
        "approach_distance_m": float(approach_distance_m),
        "pedestrian_near_distance_m": float(pedestrian_near_distance_m),
    }


def _draw_setup_preview(frame, mode: str, zebra_points: List[List[int]], reference_points: List[List[int]]):
    preview = frame.copy()
    for point in zebra_points:
        cv2.circle(preview, tuple(point), 4, (0, 215, 255), -1)
    if len(zebra_points) >= 2:
        cv2.polylines(preview, [np.array(zebra_points, dtype="int32")], False, (0, 215, 255), 2)
    if len(zebra_points) >= 3:
        cv2.polylines(preview, [np.array(zebra_points, dtype="int32")], True, (0, 215, 255), 1)

    for point in reference_points:
        cv2.circle(preview, tuple(point), 5, (255, 255, 0), -1)
    if len(reference_points) == 2:
        cv2.line(preview, tuple(reference_points[0]), tuple(reference_points[1]), (255, 255, 0), 2)

    instructions = (
        "ZEBRA: click polygon corners, Enter when done"
        if mode == "zebra"
        else "REFERENCE: click 2 points for known distance, Enter to save"
    )
    cv2.rectangle(preview, (0, 0), (preview.shape[1], 58), (20, 20, 20), -1)
    cv2.putText(preview, instructions, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(preview, "u=undo  r=reset  q=quit", (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)
    return preview


def interactive_draw_setup(video_path: str) -> Tuple[List[List[int]], List[List[int]]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError(f"Could not read first frame from video: {video_path}")

    window_name = "Draw Zebra Crossing Setup"
    mode = {"value": "zebra"}
    zebra_points: List[List[int]] = []
    reference_points: List[List[int]] = []

    def on_mouse(event, x, y, flags, userdata):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if mode["value"] == "zebra":
            zebra_points.append([int(x), int(y)])
        elif len(reference_points) < 2:
            reference_points.append([int(x), int(y)])

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        cv2.imshow(window_name, _draw_setup_preview(frame, mode["value"], zebra_points, reference_points))
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10):
            if mode["value"] == "zebra":
                if len(zebra_points) >= 3:
                    mode["value"] = "reference"
                continue
            if len(reference_points) == 2:
                break
        if key == ord("u"):
            if mode["value"] == "zebra" and zebra_points:
                zebra_points.pop()
            elif mode["value"] == "reference" and reference_points:
                reference_points.pop()
        elif key == ord("r"):
            if mode["value"] == "zebra":
                zebra_points.clear()
            else:
                reference_points.clear()
        elif key == ord("q"):
            cv2.destroyWindow(window_name)
            raise RuntimeError("Drawing cancelled.")

    cv2.destroyWindow(window_name)
    return zebra_points, reference_points


def setup_from_video(args):
    zebra_points, reference_points = interactive_draw_setup(args.video)
    setup_config = build_drawn_setup_config(
        camera_id=args.camera_id,
        zebra_points=zebra_points,
        reference_points=reference_points,
        real_distance_m=args.real_distance_m,
        zone_id=args.zone_id,
        reference_id=args.reference_id,
        approach_speed_threshold_kmh=args.approach_speed_threshold,
        pedestrian_speed_threshold_kmh=args.pedestrian_speed_threshold,
        interaction_window_seconds=args.interaction_window_seconds,
        approach_distance_m=args.approach_distance_m,
        pedestrian_near_distance_m=args.pedestrian_near_distance_m,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.safe_dump(setup_config, f, sort_keys=False)
    print(f"Saved zebra setup to {output_path}")


def build_analyzer(
    camera_id: str,
    camera_config: str,
    calibration_path: str,
    model_path: str = "yolov8n.pt",
    confidence: float = 0.25,
) -> ZebraComplianceAnalyzer:
    if not Path(camera_config).exists():
        raise FileNotFoundError(f"Camera config not found: {camera_config}")
    if not Path(calibration_path).exists():
        raise FileNotFoundError(
            f"Calibration/setup file not found: {calibration_path}. "
            "Run the setup command first, or pass an existing calibration YAML."
        )
    profiles = build_camera_profile_map(camera_config)
    camera_profile = profiles.get(camera_id)
    if camera_profile is None:
        raise ValueError(f"No camera profile found for camera_id {camera_id!r} in {camera_config!r}.")
    calibration = load_calibration(calibration_path, camera_id)
    return ZebraComplianceAnalyzer(
        camera_id=camera_id,
        camera_profile=camera_profile,
        calibration=calibration,
        detector=YoloTrackDetector(model_path=model_path, confidence=confidence),
    )


def parse_args(argv: Optional[Iterable[str]] = None):
    parser = argparse.ArgumentParser(description="Offline zebra crossing compliance video analysis")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a video and write annotated outputs")
    analyze_parser.add_argument("--video", required=True, help="Input video path")
    analyze_parser.add_argument("--camera-id", required=True, help="Camera ID from cameras.yaml")
    analyze_parser.add_argument("--camera-config", default="config/cameras.yaml", help="Camera configuration YAML")
    analyze_parser.add_argument("--calibration", required=True, help="Zebra calibration/setup YAML")
    analyze_parser.add_argument("--output-dir", required=True, help="Directory for annotated video and CSV/JSON outputs")
    analyze_parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path")
    analyze_parser.add_argument("--confidence", type=float, default=0.25, help="Detection confidence threshold")

    setup_parser = subparsers.add_parser("setup", help="Draw the zebra crossing and calibration line on the first frame")
    setup_parser.add_argument("--video", required=True, help="Input video path")
    setup_parser.add_argument("--camera-id", required=True, help="Camera ID for the generated setup YAML")
    setup_parser.add_argument("--output", required=True, help="Output setup YAML path")
    setup_parser.add_argument("--real-distance-m", type=float, required=True, help="Real-world distance in meters for the drawn reference line")
    setup_parser.add_argument("--zone-id", default="drawn_zebra_crossing", help="Zone ID saved in the setup YAML")
    setup_parser.add_argument("--reference-id", default="drawn_reference_line", help="Reference segment ID saved in the setup YAML")
    setup_parser.add_argument("--approach-speed-threshold", type=float, default=15.0, help="Vehicle speed threshold for yielding risk")
    setup_parser.add_argument("--pedestrian-speed-threshold", type=float, default=8.0, help="Pedestrian speed threshold stored in output metadata")
    setup_parser.add_argument("--interaction-window-seconds", type=float, default=3.0, help="How long a pedestrian remains active near the crossing")
    setup_parser.add_argument("--approach-distance-m", type=float, default=12.0, help="Distance from zebra zone treated as vehicle approach")
    setup_parser.add_argument("--pedestrian-near-distance-m", type=float, default=2.0, help="Distance from zebra zone treated as pedestrian near-crossing")

    parser.add_argument("--video", help=argparse.SUPPRESS)
    parser.add_argument("--camera-id", help=argparse.SUPPRESS)
    parser.add_argument("--camera-config", default="config/cameras.yaml", help=argparse.SUPPRESS)
    parser.add_argument("--calibration", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", help=argparse.SUPPRESS)
    parser.add_argument("--model", default="yolov8n.pt", help=argparse.SUPPRESS)
    parser.add_argument("--confidence", type=float, default=0.25, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None):
    args = parse_args(argv)
    try:
        if args.command == "setup":
            setup_from_video(args)
            return
        if args.command is None:
            required = ["video", "camera_id", "calibration", "output_dir"]
            missing = [name.replace("_", "-") for name in required if not getattr(args, name, None)]
            if missing:
                raise SystemExit(f"Missing required arguments: {', '.join('--' + name for name in missing)}")
        analyzer = build_analyzer(
            camera_id=args.camera_id,
            camera_config=args.camera_config,
            calibration_path=args.calibration,
            model_path=args.model,
            confidence=args.confidence,
        )
        summary = analyzer.analyze_video(args.video, args.output_dir)
        print(json.dumps(summary["outputs"], indent=2))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Error: {exc}") from None


if __name__ == "__main__":
    main()
