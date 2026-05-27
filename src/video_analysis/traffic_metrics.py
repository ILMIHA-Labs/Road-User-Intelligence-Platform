import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import cv2
import numpy as np
import yaml

from common.camera_config import DEFAULT_COUNTING_LINE_CLASSES, build_camera_profile_map
from common.event_schemas import dump_event
from edge_vision.line_counter import LineCrossingCounter
from speed_estimation.calibration import CameraCalibration
from speed_estimation.speed_calc import SpeedCalculator


TRACK_CLASSES = {"car", "bus", "truck", "motorcycle", "pedestrian", "bicycle", "rider"}
VEHICLE_CLASSES = {"car", "bus", "truck", "motorcycle"}
PEDESTRIAN_CLASSES = {"pedestrian"}
BIKE_CLASSES = {"motorcycle", "bicycle"}


class YoloTrackDetector:
    def __init__(self, model_path: str = "yolov8l.pt", confidence: float = 0.25):
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame) -> List[dict]:
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

        observations = []
        for box, track_id, conf, cls_id in zip(
            results.boxes.xyxy.cpu().numpy(),
            results.boxes.id.int().cpu().numpy(),
            results.boxes.conf.cpu().numpy(),
            results.boxes.cls.int().cpu().numpy(),
        ):
            class_name = results.names[int(cls_id)]
            if class_name == "person":
                class_name = "pedestrian"
            observations.append(
                {
                    "object_id": int(track_id),
                    "class_name": class_name,
                    "bbox": [float(value) for value in box],
                    "confidence": float(conf),
                }
            )
        return observations


def _timestamp_for_elapsed(elapsed_seconds: float) -> str:
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=elapsed_seconds)).isoformat()


def _bbox_label_anchor(bbox: List[float]):
    x1, y1, _, _ = bbox
    return int(x1), max(18, int(y1) - 8)


def _bbox_anchors(bbox: List[float]) -> Dict[str, tuple]:
    x1, y1, x2, y2 = bbox
    return {
        "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
        "bottom_center": ((x1 + x2) / 2.0, y2),
    }


def _bbox_intersection_area(first: List[float], second: List[float]) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    return width * height


def _bbox_area(bbox: List[float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _point_in_polygon(point, polygon: List[List[float]]) -> bool:
    if len(polygon) < 3:
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


def _point_segment_distance(point, start, end) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    denom = (dx * dx) + (dy * dy)
    if denom <= 1e-9:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / denom))
    closest = (sx + (t * dx), sy + (t * dy))
    return math.hypot(px - closest[0], py - closest[1])


def _point_polygon_distance(point, polygon: List[List[float]]) -> float:
    if _point_in_polygon(point, polygon):
        return 0.0
    if not polygon:
        return float("inf")
    return min(
        _point_segment_distance(
            point,
            (float(start[0]), float(start[1])),
            (float(polygon[(index + 1) % len(polygon)][0]), float(polygon[(index + 1) % len(polygon)][1])),
        )
        for index, start in enumerate(polygon)
    )


def _print_progress(current: int, total: int, width: int = 32):
    if total <= 0:
        sys.stderr.write(f"\rProcessed {current} frames")
        sys.stderr.flush()
        return
    ratio = min(1.0, max(0.0, current / total))
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    percent = ratio * 100.0
    sys.stderr.write(f"\r[{bar}] {current}/{total} frames {percent:5.1f}%")
    sys.stderr.flush()


def _normalize_line_arg(value: Optional[str]) -> Optional[List[List[float]]]:
    if not value:
        return None
    try:
        points = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("--line-points must be JSON like '[[100,0],[100,720]]'") from exc
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError("--line-points must contain exactly two points")
    normalized = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("--line-points must contain points as [x,y]")
        normalized.append([float(point[0]), float(point[1])])
    return normalized


def load_line_config(path: Optional[str]) -> Optional[List[List[float]]]:
    if not path:
        return None
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}
    return _normalize_line_points(raw.get("line_points"))


def load_zebra_config(path: Optional[str]) -> Optional[List[dict]]:
    if not path:
        return None
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}
    return normalize_zebra_zones(raw.get("zebra_zones") or [raw])


def _normalize_polygon_arg(value: Optional[str]) -> Optional[List[List[float]]]:
    if not value:
        return None
    try:
        points = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("--zebra-points must be JSON like '[[100,100],[300,100],[300,200],[100,200]]'") from exc
    return _normalize_polygon_points(points)


def _normalize_polygon_points(points) -> List[List[float]]:
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("zebra polygon must contain at least three points")
    normalized = []
    for point in points:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or not all(isinstance(value, (int, float)) for value in point)
        ):
            raise ValueError("zebra polygon points must be [x, y]")
        normalized.append([float(point[0]), float(point[1])])
    return normalized


def _normalize_line_points(points) -> List[List[float]]:
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError("line_points must contain exactly two points")
    normalized = []
    for point in points:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or not all(isinstance(value, (int, float)) for value in point)
        ):
            raise ValueError("line_points must contain points as [x, y]")
        normalized.append([float(point[0]), float(point[1])])
    return normalized


def build_counting_lines(camera_profile: dict, line_points: Optional[List[List[float]]] = None, line_id: str = "") -> List[dict]:
    if line_points:
        return [
            {
                "id": line_id,
                "label": line_id.replace("_", " ").title(),
                "points": line_points,
                "enabled": True,
                "classes": list(DEFAULT_COUNTING_LINE_CLASSES),
                "min_crossing_distance_px": 4.0,
                "reset_distance_px": 10.0,
                "min_displacement_px": 4.0,
                "min_observations": 2,
                "line_window_margin_px": 240.0,
            }
        ]
    return camera_profile.get("counting_lines") or []


def normalize_zebra_zones(zones: Optional[List[dict]]) -> List[dict]:
    normalized = []
    for index, zone in enumerate(zones or []):
        if not isinstance(zone, dict):
            continue
        points = _normalize_polygon_points(zone.get("points", []))
        zone_id = zone.get("id") or f"offline_zebra_{index + 1}"
        normalized.append(
            {
                "id": zone_id,
                "label": zone.get("label", zone_id.replace("_", " ").title()),
                "category": "zebra_crossing",
                "points": points,
            }
        )
    return normalized


def build_zebra_zones(camera_profile: dict, zebra_points: Optional[List[List[float]]] = None, zebra_config: Optional[List[dict]] = None) -> List[dict]:
    if zebra_points:
        return normalize_zebra_zones(
            [{"id": "offline_zebra_crossing", "label": "", "points": zebra_points}]
        )
    if zebra_config is not None:
        return zebra_config
    return [
        zone for zone in camera_profile.get("zones", [])
        if zone.get("category") == "zebra_crossing" and len(zone.get("points", [])) >= 3
    ]


def build_zebra_setup_config(camera_id: str, zebra_points: List[List[float]], zone_id: str = "offline_zebra_crossing") -> dict:
    return {
        "camera_id": camera_id,
        "zebra_zones": [
            {
                "id": zone_id,
                "label": zone_id.replace("_", " ").title(),
                "category": "zebra_crossing",
                "points": _normalize_polygon_points(zebra_points),
            }
        ],
    }


def build_line_setup_config(camera_id: str, line_points: List[List[float]], line_id: str = "") -> dict:
    normalized_points = _normalize_line_points(line_points)
    return {
        "camera_id": camera_id,
        "line_id": line_id,
        "line_points": normalized_points,
    }


def _draw_line_preview(frame, line_points: List[List[int]]):
    preview = frame.copy()
    for point in line_points:
        cv2.circle(preview, tuple(point), 5, (0, 215, 255), -1)
    if len(line_points) == 2:
        cv2.line(preview, tuple(line_points[0]), tuple(line_points[1]), (0, 215, 255), 2)

    cv2.rectangle(preview, (0, 0), (preview.shape[1], 58), (20, 20, 20), -1)
    cv2.putText(
        preview,
        "Click 2 points for the counting line, then press Enter",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        preview,
        "u=undo  r=reset  q=quit",
        (12, 46),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    return preview


def _draw_zebra_preview(frame, zebra_points: List[List[int]]):
    preview = frame.copy()
    for point in zebra_points:
        cv2.circle(preview, tuple(point), 5, (0, 215, 255), -1)
    if len(zebra_points) >= 2:
        cv2.polylines(preview, [np.array(zebra_points, dtype="int32")], isClosed=False, color=(0, 215, 255), thickness=2)
    if len(zebra_points) >= 3:
        cv2.polylines(preview, [np.array(zebra_points, dtype="int32")], isClosed=True, color=(0, 215, 255), thickness=1)

    cv2.rectangle(preview, (0, 0), (preview.shape[1], 58), (20, 20, 20), -1)
    cv2.putText(
        preview,
        "Click zebra polygon corners, then press Enter",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        preview,
        "u=undo  r=reset  q=quit",
        (12, 46),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    return preview


def _draw_multi_zebra_preview(frame, zebra_zones: List[List[List[int]]], current_points: List[List[int]]):
    preview = frame.copy()
    colors = [(255, 0, 255), (0, 215, 255), (60, 220, 60), (255, 150, 0)]
    for index, points in enumerate(zebra_zones):
        if len(points) < 3:
            continue
        color = colors[index % len(colors)]
        np_points = np.array(points, dtype="int32")
        cv2.polylines(preview, [np_points], isClosed=True, color=color, thickness=2)
        cv2.putText(
            preview,
            f"Z{index + 1}",
            tuple(np_points[0]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    for point in current_points:
        cv2.circle(preview, tuple(point), 5, (0, 215, 255), -1)
    if len(current_points) >= 2:
        cv2.polylines(preview, [np.array(current_points, dtype="int32")], isClosed=False, color=(0, 215, 255), thickness=2)
    if len(current_points) >= 3:
        cv2.polylines(preview, [np.array(current_points, dtype="int32")], isClosed=True, color=(0, 215, 255), thickness=1)

    cv2.rectangle(preview, (0, 0), (preview.shape[1], 78), (20, 20, 20), -1)
    cv2.putText(
        preview,
        "Click zebra polygon corners. Enter/add = save current zone.",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        preview,
        "n=next zone  s=save all  u=undo  r=reset current  q=quit",
        (12, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        preview,
        f"Saved zones: {len(zebra_zones)}",
        (12, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    return preview


def interactive_draw_line(video_path: str) -> List[List[int]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError(f"Could not read first frame from video: {video_path}")

    window_name = "Draw Traffic Count Line"
    line_points: List[List[int]] = []

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN and len(line_points) < 2:
            line_points.append([int(x), int(y)])

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        cv2.imshow(window_name, _draw_line_preview(frame, line_points))
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and len(line_points) == 2:
            break
        if key == ord("u") and line_points:
            line_points.pop()
        elif key == ord("r"):
            line_points.clear()
        elif key == ord("q"):
            cv2.destroyWindow(window_name)
            raise RuntimeError("Line drawing cancelled.")

    cv2.destroyWindow(window_name)
    return line_points


def interactive_draw_zebra(video_path: str) -> List[List[int]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError(f"Could not read first frame from video: {video_path}")

    window_name = "Draw Zebra Crossing Polygon"
    zebra_points: List[List[int]] = []

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            zebra_points.append([int(x), int(y)])

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        cv2.imshow(window_name, _draw_zebra_preview(frame, zebra_points))
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and len(zebra_points) >= 3:
            break
        if key == ord("u") and zebra_points:
            zebra_points.pop()
        elif key == ord("r"):
            zebra_points.clear()
        elif key == ord("q"):
            cv2.destroyWindow(window_name)
            raise RuntimeError("Zebra drawing cancelled.")

    cv2.destroyWindow(window_name)
    return zebra_points


def interactive_draw_zebras(video_path: str) -> List[List[List[int]]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError(f"Could not read first frame from video: {video_path}")

    window_name = "Draw Zebra Crossing Polygons"
    zebra_zones: List[List[List[int]]] = []
    current_points: List[List[int]] = []

    def save_current():
        if len(current_points) < 3:
            return False
        zebra_zones.append([list(point) for point in current_points])
        current_points.clear()
        return True

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            current_points.append([int(x), int(y)])

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        cv2.imshow(window_name, _draw_multi_zebra_preview(frame, zebra_zones, current_points))
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10, ord("n")):
            save_current()
        elif key == ord("s"):
            save_current()
            if zebra_zones:
                break
        elif key == ord("u") and current_points:
            current_points.pop()
        elif key == ord("r"):
            current_points.clear()
        elif key == ord("q"):
            cv2.destroyWindow(window_name)
            raise RuntimeError("Zebra drawing cancelled.")

    cv2.destroyWindow(window_name)
    return zebra_zones


def setup_line_from_video(args):
    line_points = interactive_draw_line(args.video)
    setup_config = build_line_setup_config(args.camera_id, line_points, line_id=args.line_id)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.safe_dump(setup_config, f, sort_keys=False)
    print(f"Saved counting line setup to {output_path}")


def setup_zebra_from_video(args):
    if getattr(args, "multi", False):
        zebra_polygons = interactive_draw_zebras(args.video)
        zones = []
        for index, zebra_points in enumerate(zebra_polygons, start=1):
            zone_id = args.zone_id if len(zebra_polygons) == 1 else f"{args.zone_id}_{index}"
            zones.append(
                {
                    "id": zone_id,
                    "label": f"Z{index}",
                    "category": "zebra_crossing",
                    "points": _normalize_polygon_points(zebra_points),
                }
            )
        setup_config = {"camera_id": args.camera_id, "zebra_zones": zones}
    else:
        zebra_points = interactive_draw_zebra(args.video)
        setup_config = build_zebra_setup_config(args.camera_id, zebra_points, zone_id=args.zone_id)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.safe_dump(setup_config, f, sort_keys=False)
    print(f"Saved zebra crossing setup to {output_path}")


class TrafficMetricsAnalyzer:
    def __init__(
        self,
        camera_id: str,
        camera_profile: dict,
        detector=None,
        counting_lines: Optional[List[dict]] = None,
        zebra_zones: Optional[List[dict]] = None,
        pixels_per_meter: Optional[float] = None,
        zebra_speed_threshold_kmh: float = 15.0,
        zebra_zone_margin_m: float = 2.0,
        zebra_interaction_window_seconds: float = 3.0,
        zebra_speed_trend_deadband_kmh: float = 2.0,
        filter_riders_from_pedestrians: bool = True,
        max_riders_per_bike: int = 2,
    ):
        self.camera_id = camera_id
        self.camera_profile = camera_profile
        self.detector = detector or YoloTrackDetector()
        self.counting_lines = counting_lines if counting_lines is not None else camera_profile.get("counting_lines", [])
        if not self.counting_lines:
            raise ValueError("No counting line configured. Add a counting line to cameras.yaml or pass --line-points.")
        self.zebra_zones = zebra_zones or []

        self.pixels_per_meter = float(pixels_per_meter or camera_profile.get("pixels_per_meter", 25.0))
        self.zebra_speed_threshold_kmh = float(zebra_speed_threshold_kmh)
        self.zebra_zone_margin_m = float(zebra_zone_margin_m)
        self.zebra_interaction_window_seconds = float(zebra_interaction_window_seconds)
        self.zebra_speed_trend_deadband_kmh = float(zebra_speed_trend_deadband_kmh)
        self.filter_riders_from_pedestrians = bool(filter_riders_from_pedestrians)
        self.max_riders_per_bike = int(max_riders_per_bike)
        self.speed_calculator = SpeedCalculator(
            calibration=CameraCalibration(pixels_per_meter=self.pixels_per_meter),
            history_size=int(camera_profile.get("speed_history_size", 5)),
            max_speed_kmh=float(camera_profile.get("speed_max_kmh", 200.0)),
            min_time_delta_seconds=float(camera_profile.get("speed_min_time_delta_seconds", 0.0)),
            smoothing_alpha=float(camera_profile.get("speed_smoothing_alpha", 1.0)),
            outlier_mode=camera_profile.get("speed_outlier_mode", "cap"),
        )
        self.line_counter = LineCrossingCounter(self.counting_lines)
        self.track_rows: List[dict] = []
        self.crossing_rows: List[dict] = []
        self.object_summaries: Dict[int, dict] = {}
        self.running_counts_by_class = defaultdict(int)
        self.running_counts_by_direction = defaultdict(int)
        self.recent_zebra_pedestrians: Dict[tuple, dict] = {}
        self.zebra_event_keys = set()
        self.zebra_event_rows: List[dict] = []
        self.zebra_occupancy_rows: List[dict] = []
        self.zebra_approach_samples = defaultdict(list)
        self.rider_filtered_pedestrians_count = 0

    def _short_zone_label(self, zone: dict, index: int) -> str:
        label = zone.get("label") or zone.get("id") or f"Z{index + 1}"
        if isinstance(label, str) and len(label) <= 4:
            return label
        return f"Z{index + 1}"

    def _zone_states_for_bbox(self, bbox: List[float]) -> List[dict]:
        states = []
        anchors = _bbox_anchors(bbox)
        for zone in self.zebra_zones:
            polygon = zone.get("points", [])
            anchor_distances = [
                _point_polygon_distance(anchor, polygon)
                for anchor in anchors.values()
            ]
            distance_px = min(anchor_distances) if anchor_distances else float("inf")
            inside = any(_point_in_polygon(anchor, polygon) for anchor in anchors.values())
            distance_m = distance_px / self.pixels_per_meter
            states.append(
                {
                    "zone_id": zone.get("id"),
                    "inside": bool(inside),
                    "near": bool(inside or distance_m <= self.zebra_zone_margin_m),
                    "distance_m": round(float(distance_m), 2),
                }
            )
        return states

    def _zebra_state_for_row(self, row: dict) -> dict:
        if not self.zebra_zones:
            return {
                "zebra_zone_id": None,
                "inside_zebra": False,
                "near_zebra": False,
                "distance_to_zebra_m": None,
                "inside_zebra_zone_ids": "[]",
                "near_zebra_zone_ids": "[]",
                "_zebra_zone_states": [],
            }

        bbox = json.loads(row["bbox"])
        zone_states = self._zone_states_for_bbox(bbox)
        best_state = min(zone_states, key=lambda state: state["distance_m"]) if zone_states else None
        inside_zone_ids = [state["zone_id"] for state in zone_states if state["inside"]]
        near_zone_ids = [state["zone_id"] for state in zone_states if state["near"]]
        return {
            "zebra_zone_id": best_state["zone_id"] if best_state else None,
            "inside_zebra": bool(best_state and best_state["inside"]),
            "near_zebra": bool(best_state and best_state["near"]),
            "distance_to_zebra_m": best_state["distance_m"] if best_state else None,
            "inside_zebra_zone_ids": json.dumps(inside_zone_ids),
            "near_zebra_zone_ids": json.dumps(near_zone_ids),
            "_zebra_zone_states": zone_states,
        }

    def _associate_riders(self, observations: List[dict]) -> List[dict]:
        if not self.filter_riders_from_pedestrians:
            return observations

        bikes = [
            observation for observation in observations
            if observation.get("class_name") in BIKE_CLASSES
        ]
        pedestrians = [
            observation for observation in observations
            if observation.get("class_name") in PEDESTRIAN_CLASSES
        ]
        if not bikes or not pedestrians:
            return observations

        candidates = []
        for pedestrian in pedestrians:
            ped_bbox = pedestrian["bbox"]
            px1, py1, px2, py2 = ped_bbox
            ped_center_x = (px1 + px2) / 2.0
            ped_area = max(_bbox_area(ped_bbox), 1e-9)
            for bike in bikes:
                bike_bbox = bike["bbox"]
                bx1, by1, bx2, by2 = bike_bbox
                bike_width = max(bx2 - bx1, 1.0)
                bike_height = max(by2 - by1, 1.0)
                bike_center_x = (bx1 + bx2) / 2.0
                horizontal_distance = abs(ped_center_x - bike_center_x)
                overlap_ratio = _bbox_intersection_area(ped_bbox, bike_bbox) / ped_area
                above_or_overlapping = py2 >= by1 - (0.35 * bike_height) and py1 <= by2
                horizontally_close = horizontal_distance <= bike_width * 0.75
                if not above_or_overlapping or not horizontally_close:
                    continue
                score = overlap_ratio - (horizontal_distance / bike_width)
                candidates.append((score, pedestrian["object_id"], bike["object_id"], overlap_ratio, horizontal_distance))

        assigned_pedestrians = set()
        riders_by_bike = defaultdict(int)
        rider_matches = {}
        for _, pedestrian_id, bike_id, overlap_ratio, horizontal_distance in sorted(candidates, reverse=True):
            if pedestrian_id in assigned_pedestrians:
                continue
            if riders_by_bike[bike_id] >= self.max_riders_per_bike:
                continue
            assigned_pedestrians.add(pedestrian_id)
            riders_by_bike[bike_id] += 1
            rider_matches[pedestrian_id] = {
                "associated_vehicle_id": bike_id,
                "rider_overlap_ratio": round(float(overlap_ratio), 4),
                "rider_horizontal_distance_px": round(float(horizontal_distance), 2),
            }

        for observation in observations:
            match = rider_matches.get(observation.get("object_id"))
            if match:
                observation["is_rider"] = True
                observation["original_class_name"] = observation.get("class_name")
                observation["class_name"] = "rider"
                observation.update(match)
            else:
                observation["is_rider"] = False
        self.rider_filtered_pedestrians_count += len(rider_matches)
        return observations

    def _update_vehicle_approach_samples(self, row: dict):
        if row["class"] not in VEHICLE_CLASSES or row.get("speed_kmh") is None:
            return
        for state in row.get("_zebra_zone_states", []):
            if not state["near"]:
                continue
            key = (row["object_id"], state["zone_id"])
            self.zebra_approach_samples[key].append(
                {
                    "elapsed_seconds": row["elapsed_seconds"],
                    "speed_kmh": float(row["speed_kmh"]),
                    "distance_m": state["distance_m"],
                }
            )

    def _approach_trend_for_vehicle_zone(self, object_id: int, zone_id: str) -> dict:
        samples = self.zebra_approach_samples.get((object_id, zone_id), [])
        if len(samples) < 2:
            return {
                "vehicle_speed_trend": "insufficient_data",
                "approach_start_speed_kmh": None,
                "approach_end_speed_kmh": None,
                "approach_delta_kmh": None,
                "approach_samples": len(samples),
            }
        start_speed = samples[0]["speed_kmh"]
        end_speed = samples[-1]["speed_kmh"]
        delta = end_speed - start_speed
        if delta <= -self.zebra_speed_trend_deadband_kmh:
            trend = "decreased"
        elif delta >= self.zebra_speed_trend_deadband_kmh:
            trend = "increased"
        else:
            trend = "constant"
        return {
            "vehicle_speed_trend": trend,
            "approach_start_speed_kmh": round(start_speed, 2),
            "approach_end_speed_kmh": round(end_speed, 2),
            "approach_delta_kmh": round(delta, 2),
            "approach_samples": len(samples),
        }

    def _update_zebra_occupancy(self, frame_number: int, elapsed_seconds: float, frame_rows: List[dict]) -> List[dict]:
        rows = []
        for zone in self.zebra_zones:
            zone_id = zone.get("id")
            objects_in_zone = [
                row for row in frame_rows
                if any(state["zone_id"] == zone_id and state["inside"] for state in row.get("_zebra_zone_states", []))
            ]
            class_counts = defaultdict(int)
            for row in objects_in_zone:
                if row.get("is_rider") and row["class"] in PEDESTRIAN_CLASSES:
                    class_counts["rider"] += 1
                else:
                    class_counts[row["class"]] += 1
            occupancy = {
                "frame_number": frame_number,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "zone_id": zone_id,
                "objects_in_zone": len(objects_in_zone),
                "vehicles_in_zone": sum(1 for row in objects_in_zone if row["class"] in VEHICLE_CLASSES),
                "pedestrians_in_zone": sum(1 for row in objects_in_zone if row["class"] in PEDESTRIAN_CLASSES and not row.get("is_rider")),
                "bikes_in_zone": sum(1 for row in objects_in_zone if row["class"] in BIKE_CLASSES),
                "class_counts_json": json.dumps(dict(sorted(class_counts.items()))),
            }
            rows.append(occupancy)
            self.zebra_occupancy_rows.append(occupancy)
        return rows

    def _update_zebra_events(self, frame_number: int, elapsed_seconds: float, frame_rows: List[dict]) -> List[dict]:
        if not self.zebra_zones:
            return []

        active_pedestrians_by_zone = defaultdict(list)
        for row in frame_rows:
            if row["class"] not in PEDESTRIAN_CLASSES:
                continue
            if row.get("is_rider"):
                continue
            for state in row.get("_zebra_zone_states", []):
                if not state["near"]:
                    continue
                stored = dict(row)
                stored["zebra_zone_id"] = state["zone_id"]
                stored["distance_to_zebra_m"] = state["distance_m"]
                stored["_last_seen_seconds"] = elapsed_seconds
                self.recent_zebra_pedestrians[(row["object_id"], state["zone_id"])] = stored
                active_pedestrians_by_zone[state["zone_id"]].append(stored)

        active_keys = {
            (row["object_id"], row["zebra_zone_id"])
            for zone_rows in active_pedestrians_by_zone.values()
            for row in zone_rows
        }
        for key, row in self.recent_zebra_pedestrians.items():
            if key in active_keys:
                continue
            if elapsed_seconds - row["_last_seen_seconds"] <= self.zebra_interaction_window_seconds:
                active_pedestrians_by_zone[row["zebra_zone_id"]].append(row)
        stale_keys = [
            key for key, row in self.recent_zebra_pedestrians.items()
            if elapsed_seconds - row["_last_seen_seconds"] > self.zebra_interaction_window_seconds
        ]
        for key in stale_keys:
            self.recent_zebra_pedestrians.pop(key, None)

        if not active_pedestrians_by_zone:
            return []

        frame_events = []
        for vehicle in frame_rows:
            if vehicle["class"] not in VEHICLE_CLASSES:
                continue
            speed = vehicle.get("speed_kmh")
            if speed is None or float(speed) < self.zebra_speed_threshold_kmh:
                continue
            for state in vehicle.get("_zebra_zone_states", []):
                if not state["near"]:
                    continue
                matching_pedestrians = active_pedestrians_by_zone.get(state["zone_id"], [])
                if not matching_pedestrians:
                    continue
                pedestrian = min(
                    matching_pedestrians,
                    key=lambda candidate: candidate.get("distance_to_zebra_m") if candidate.get("distance_to_zebra_m") is not None else 999999.0,
                )
                event_type = "zebra_crossing_violation" if state["inside"] else "zebra_yielding_risk"
                event_key = (event_type, vehicle["object_id"], pedestrian["object_id"], state["zone_id"])
                if event_key in self.zebra_event_keys:
                    continue
                self.zebra_event_keys.add(event_key)
                event = {
                    "event_type": event_type,
                    "camera_id": self.camera_id,
                    "frame_number": frame_number,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "zone_id": state["zone_id"],
                    "vehicle_object_id": vehicle["object_id"],
                    "vehicle_class": vehicle["class"],
                    "vehicle_speed_kmh": round(float(speed), 2),
                    "vehicle_distance_to_zebra_m": state["distance_m"],
                    "pedestrian_object_id": pedestrian["object_id"],
                    "pedestrian_speed_kmh": pedestrian.get("speed_kmh"),
                    "pedestrian_distance_to_zebra_m": pedestrian.get("distance_to_zebra_m"),
                    "rider_filtered_pedestrians_count": self.rider_filtered_pedestrians_count,
                }
                event.update(self._approach_trend_for_vehicle_zone(vehicle["object_id"], state["zone_id"]))
                self.zebra_event_rows.append(event)
                frame_events.append(event)
        return frame_events

    def _update_object_summary(self, observation: dict, speed_kmh: Optional[float]):
        summary = self.object_summaries.setdefault(
            observation["object_id"],
            {
                "object_id": observation["object_id"],
                "class": observation["class_name"],
                "frames_seen": 0,
                "max_speed_kmh": None,
                "avg_speed_kmh": None,
                "_speed_samples": [],
            },
        )
        summary["class"] = observation["class_name"]
        summary["frames_seen"] += 1
        if speed_kmh is not None:
            summary["_speed_samples"].append(float(speed_kmh))
            summary["max_speed_kmh"] = max(summary["max_speed_kmh"] or 0.0, float(speed_kmh))
            summary["avg_speed_kmh"] = sum(summary["_speed_samples"]) / len(summary["_speed_samples"])

    def analyze_frame(self, frame, frame_number: int, elapsed_seconds: float):
        observations = [
            observation for observation in self.detector.detect(frame)
            if observation.get("class_name") in TRACK_CLASSES
        ]
        observations = self._associate_riders(observations)
        timestamp = _timestamp_for_elapsed(elapsed_seconds)
        frame_rows = []

        for observation in observations:
            speed = self.speed_calculator.update_position(
                observation["object_id"],
                timestamp,
                observation["bbox"],
            )
            self._update_object_summary(observation, speed)
            row = {
                "frame_number": frame_number,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "camera_id": self.camera_id,
                "object_id": observation["object_id"],
                "class": observation["class_name"],
                "confidence": round(float(observation.get("confidence", 0.0)), 4),
                "bbox": json.dumps([round(float(value), 2) for value in observation["bbox"]]),
                "speed_kmh": round(float(speed), 2) if speed is not None else None,
                "is_rider": bool(observation.get("is_rider", False)),
                "associated_vehicle_id": observation.get("associated_vehicle_id"),
            }
            row.update(self._zebra_state_for_row(row))
            frame_rows.append(row)
            self._update_vehicle_approach_samples(row)
            csv_row = dict(row)
            csv_row.pop("_zebra_zone_states", None)
            self.track_rows.append(csv_row)

        crossing_events = self.line_counter.process_tracks(
            camera_id=self.camera_id,
            frame_number=frame_number,
            tracks=observations,
            timestamp=timestamp,
        )
        frame_crossings = []
        for event in crossing_events:
            row = dump_event(event)
            row["elapsed_seconds"] = round(elapsed_seconds, 3)
            self.crossing_rows.append(row)
            self.running_counts_by_class[row["class"]] += 1
            self.running_counts_by_direction[row["direction"]] += 1
            frame_crossings.append(row)
        frame_zebra_occupancy = self._update_zebra_occupancy(frame_number, elapsed_seconds, frame_rows)
        frame_zebra_events = self._update_zebra_events(frame_number, elapsed_seconds, frame_rows)
        return frame_rows, frame_crossings, frame_zebra_events, frame_zebra_occupancy

    def _draw_count_overlay(self, annotated):
        lines = [f"Total: {len(self.crossing_rows)}"]
        for class_name, count in sorted(self.running_counts_by_class.items()):
            lines.append(f"{self._short_class_name(class_name)}: {count}")
        if self.running_counts_by_direction:
            direction_text = "  ".join(
                f"{self._short_direction(direction)}:{count}" for direction, count in sorted(self.running_counts_by_direction.items())
            )
            lines.append(direction_text)
        speed_metrics = self._running_speed_metrics_by_class()
        for class_name, metrics in sorted(speed_metrics.items()):
            lines.append(
                f"{self._short_class_name(class_name)} Vmax {metrics['max_speed_kmh']:.1f} P85 {metrics['p85_speed_kmh']:.1f}"
            )
        for row in self._latest_zebra_occupancy_rows():
            lines.append(
                f"{self._short_zone_id(row['zone_id'])} veh:{row['vehicles_in_zone']} ped:{row['pedestrians_in_zone']} bike:{row['bikes_in_zone']}"
            )

        padding = 10
        font_scale = 0.46
        thickness = 1
        line_height = 20
        max_text_width = 0
        for text in lines:
            text_width, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
            max_text_width = max(max_text_width, text_width)
        box_width = min(max(150, max_text_width + (padding * 2)), annotated.shape[1] - 24)
        box_height = padding * 2 + line_height * len(lines)
        x1 = annotated.shape[1] - box_width - 12
        y1 = 12
        x2 = annotated.shape[1] - 12
        y2 = y1 + box_height

        overlay = annotated.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.72, annotated, 0.28, 0, annotated)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 215, 255), 1)

        for index, text in enumerate(lines):
            y = y1 + padding + 16 + (index * line_height)
            color = (255, 255, 255) if index == 0 else (220, 235, 235)
            cv2.putText(
                annotated,
                text,
                (x1 + padding, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                thickness,
                cv2.LINE_AA,
            )

    @staticmethod
    def _short_class_name(class_name: str) -> str:
        labels = {
            "pedestrian": "ped",
            "motorcycle": "moto",
            "bicycle": "bike",
            "rider": "rider",
        }
        return labels.get(class_name, class_name)

    @staticmethod
    def _short_direction(direction: str) -> str:
        return {"a_to_b": "A>B", "b_to_a": "B>A"}.get(direction, direction)

    @staticmethod
    def _short_zone_id(zone_id: str) -> str:
        if not zone_id:
            return "Z?"
        if len(str(zone_id)) <= 4:
            return str(zone_id)
        digits = "".join(ch for ch in str(zone_id) if ch.isdigit())
        return f"Z{digits}" if digits else str(zone_id)[:4]

    def _latest_zebra_occupancy_rows(self) -> List[dict]:
        if not self.zebra_occupancy_rows:
            return []
        latest_frame = self.zebra_occupancy_rows[-1]["frame_number"]
        return [row for row in self.zebra_occupancy_rows if row["frame_number"] == latest_frame]

    def _running_speed_metrics_by_class(self) -> dict:
        speeds_by_class = defaultdict(list)
        for summary in self.object_summaries.values():
            for speed in summary["_speed_samples"]:
                speeds_by_class[summary["class"]].append(speed)

        metrics_by_class = {}
        for class_name, speeds in speeds_by_class.items():
            sorted_speeds = sorted(speeds)
            p85_index = min(len(sorted_speeds) - 1, int(round((len(sorted_speeds) - 1) * 0.85)))
            metrics_by_class[class_name] = {
                "max_speed_kmh": round(max(speeds), 2),
                "p85_speed_kmh": round(sorted_speeds[p85_index], 2),
                "samples": len(speeds),
            }
        return metrics_by_class

    def annotate_frame(self, frame, frame_rows: List[dict], frame_crossings: List[dict], frame_zebra_events: Optional[List[dict]] = None):
        annotated = frame.copy()
        frame_zebra_events = frame_zebra_events or []
        for zone in self.zebra_zones:
            zone_index = self.zebra_zones.index(zone)
            points = np.array(zone.get("points", []), dtype="int32")
            if len(points) >= 3:
                cv2.polylines(annotated, [points], isClosed=True, color=(255, 0, 255), thickness=2)
                label_point = tuple(points[0])
                cv2.putText(
                    annotated,
                    self._short_zone_label(zone, zone_index),
                    (int(label_point[0]), max(20, int(label_point[1]) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
        for line in self.counting_lines:
            points = line.get("points", [])
            if len(points) != 2:
                continue
            start = tuple(int(value) for value in points[0])
            end = tuple(int(value) for value in points[1])
            cv2.line(annotated, start, end, (0, 215, 255), 2)
            cv2.putText(
                annotated,
                line.get("label", line.get("id", "count_line")),
                (start[0], max(20, start[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

        crossing_ids = {row["object_id"] for row in frame_crossings}
        zebra_vehicle_ids = {row["vehicle_object_id"] for row in frame_zebra_events}
        zebra_pedestrian_ids = {row["pedestrian_object_id"] for row in frame_zebra_events}
        for row in frame_rows:
            bbox = json.loads(row["bbox"])
            x1, y1, x2, y2 = [int(value) for value in bbox]
            color = (0, 0, 255) if row["object_id"] in crossing_ids else (60, 220, 60)
            if row["object_id"] in zebra_vehicle_ids:
                color = (0, 0, 255)
            elif row["object_id"] in zebra_pedestrian_ids:
                color = (0, 165, 255)
            elif row.get("is_rider"):
                color = (255, 150, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            speed = "--" if row["speed_kmh"] is None else f"{row['speed_kmh']:.1f}km/h"
            zebra_label = " zebra" if row.get("near_zebra") else ""
            class_label = "rider" if row.get("is_rider") else row["class"]
            cv2.putText(
                annotated,
                f"#{row['object_id']} {class_label} {speed}{zebra_label}",
                _bbox_label_anchor(bbox),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        if frame_crossings:
            banner = " | ".join(f"{row['class']} {row['direction']}" for row in frame_crossings)
            cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 36), (0, 80, 0), -1)
            cv2.putText(annotated, banner[:100], (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        if frame_zebra_events:
            banner = " | ".join(row["event_type"] for row in frame_zebra_events)
            y1 = 38 if frame_crossings else 0
            cv2.rectangle(annotated, (0, y1), (annotated.shape[1], y1 + 36), (130, 0, 130), -1)
            cv2.putText(annotated, banner[:100], (12, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        self._draw_count_overlay(annotated)
        return annotated

    def _metric_summary(self, duration_seconds: float) -> dict:
        counts_by_class = defaultdict(int)
        counts_by_line = defaultdict(int)
        counts_by_direction = defaultdict(int)
        for line in self.counting_lines:
            line_id = line.get("id")
            if line_id:
                counts_by_line[line_id] += 0
        for row in self.crossing_rows:
            counts_by_class[row["class"]] += 1
            counts_by_line[row["line_id"]] += 1
            counts_by_direction[row["direction"]] += 1

        speeds_by_class = defaultdict(list)
        for summary in self.object_summaries.values():
            for speed in summary["_speed_samples"]:
                speeds_by_class[summary["class"]].append(speed)

        speed_metrics_by_class = {}
        for class_name, speeds in speeds_by_class.items():
            sorted_speeds = sorted(speeds)
            p85_index = min(len(sorted_speeds) - 1, int(round((len(sorted_speeds) - 1) * 0.85)))
            speed_metrics_by_class[class_name] = {
                "avg_speed_kmh": round(sum(speeds) / len(speeds), 2),
                "max_speed_kmh": round(max(speeds), 2),
                "p85_speed_kmh": round(sorted_speeds[p85_index], 2),
                "samples": len(speeds),
            }

        duration_minutes = max(duration_seconds / 60.0, 1e-9)
        return {
            "total_crossings": len(self.crossing_rows),
            "counts_by_class": dict(sorted(counts_by_class.items())),
            "counts_by_line": dict(sorted(counts_by_line.items())),
            "counts_by_direction": dict(sorted(counts_by_direction.items())),
            "flow_rate_per_minute": round(len(self.crossing_rows) / duration_minutes, 2),
            "speed_metrics_by_class": speed_metrics_by_class,
        }

    def _zebra_metric_summary(self) -> dict:
        events_by_type = defaultdict(int)
        by_zone = {}
        for zone in self.zebra_zones:
            zone_id = zone.get("id")
            zone_occupancy = [row for row in self.zebra_occupancy_rows if row["zone_id"] == zone_id]
            zone_events = [row for row in self.zebra_event_rows if row["zone_id"] == zone_id]
            trend_counts = defaultdict(int)
            vehicle_zone_ids = {
                object_id for object_id, sample_zone_id in self.zebra_approach_samples.keys()
                if sample_zone_id == zone_id
            }
            for object_id in vehicle_zone_ids:
                trend = self._approach_trend_for_vehicle_zone(object_id, zone_id)["vehicle_speed_trend"]
                trend_counts[trend] += 1
            for row in zone_events:
                events_by_type[row["event_type"]] += 1
            unique_objects = set()
            for row in self.track_rows:
                inside_zone_ids = set(json.loads(row.get("inside_zebra_zone_ids") or "[]"))
                if zone_id in inside_zone_ids:
                    unique_objects.add(row["object_id"])
            by_zone[zone_id] = {
                "events": len(zone_events),
                "zebra_yielding_risk": sum(1 for row in zone_events if row["event_type"] == "zebra_yielding_risk"),
                "zebra_crossing_violation": sum(1 for row in zone_events if row["event_type"] == "zebra_crossing_violation"),
                "unique_objects_in_zone": len(unique_objects),
                "max_objects_in_zone": max((row["objects_in_zone"] for row in zone_occupancy), default=0),
                "max_vehicles_in_zone": max((row["vehicles_in_zone"] for row in zone_occupancy), default=0),
                "max_pedestrians_in_zone": max((row["pedestrians_in_zone"] for row in zone_occupancy), default=0),
                "vehicle_approach_trends": dict(sorted(trend_counts.items())),
            }
        return {
            "events": len(self.zebra_event_rows),
            "zebra_yielding_risk": events_by_type["zebra_yielding_risk"],
            "zebra_crossing_violation": events_by_type["zebra_crossing_violation"],
            "rider_filtered_pedestrians_count": self.rider_filtered_pedestrians_count,
            "by_zone": by_zone,
        }

    def _object_summary_rows(self) -> List[dict]:
        rows = []
        for summary in self.object_summaries.values():
            rows.append(
                {
                    "object_id": summary["object_id"],
                    "class": summary["class"],
                    "frames_seen": summary["frames_seen"],
                    "max_speed_kmh": round(summary["max_speed_kmh"], 2) if summary["max_speed_kmh"] is not None else None,
                    "avg_speed_kmh": round(summary["avg_speed_kmh"], 2) if summary["avg_speed_kmh"] is not None else None,
                }
            )
        return sorted(rows, key=lambda row: row["object_id"])

    def analyze_video(
        self,
        video_path: str,
        output_dir: str,
        show_progress: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
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
        writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

        frame_number = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_number += 1
                elapsed_seconds = (frame_number - 1) / fps
                frame_rows, frame_crossings, frame_zebra_events, _ = self.analyze_frame(frame, frame_number, elapsed_seconds)
                writer.write(self.annotate_frame(frame, frame_rows, frame_crossings, frame_zebra_events))
                if show_progress:
                    _print_progress(frame_number, frame_count)
                if progress_callback is not None:
                    progress_callback(frame_number, frame_count)
        finally:
            capture.release()
            writer.release()
            if show_progress:
                sys.stderr.write("\n")
                sys.stderr.flush()

        duration_seconds = frame_number / fps if fps else 0.0
        summary_path = output_path / "summary.json"
        metrics_path = output_path / "metrics.json"
        crossings_path = output_path / "crossings.csv"
        zebra_events_path = output_path / "zebra_events.csv"
        zebra_occupancy_path = output_path / "zebra_occupancy.csv"
        tracks_path = output_path / "tracks.csv"
        metrics = self._metric_summary(duration_seconds)
        summary = {
            "mode": "traffic_metrics",
            "camera_id": self.camera_id,
            "video": {
                "path": str(video_path),
                "fps": fps,
                "width": width,
                "height": height,
                "frame_count": frame_count,
                "processed_frames": frame_number,
                "duration_seconds": round(duration_seconds, 3),
            },
            "calibration": {
                "pixels_per_meter": self.pixels_per_meter,
                "source": "pixels_per_meter",
            },
            "counting_lines": self.counting_lines,
            "zebra_zones": self.zebra_zones,
            "metrics": metrics,
            "zebra_metrics": self._zebra_metric_summary(),
            "objects": self._object_summary_rows(),
            "outputs": {
                "annotated_video": str(writer_path),
                "summary_json": str(summary_path),
                "metrics_json": str(metrics_path),
                "crossings_csv": str(crossings_path),
                "zebra_events_csv": str(zebra_events_path),
                "zebra_occupancy_csv": str(zebra_occupancy_path),
                "tracks_csv": str(tracks_path),
            },
        }

        self._write_csv(crossings_path, self.crossing_rows, crossing_fieldnames())
        self._write_csv(zebra_events_path, self.zebra_event_rows, zebra_event_fieldnames())
        self._write_csv(zebra_occupancy_path, self.zebra_occupancy_rows, zebra_occupancy_fieldnames())
        self._write_csv(tracks_path, self.track_rows, track_fieldnames())
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        return summary

    @staticmethod
    def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})


def crossing_fieldnames() -> List[str]:
    return [
        "camera_id",
        "line_id",
        "line_label",
        "object_id",
        "class",
        "direction",
        "timestamp",
        "frame_number",
        "elapsed_seconds",
        "source",
    ]


def zebra_event_fieldnames() -> List[str]:
    return [
        "event_type",
        "camera_id",
        "frame_number",
        "elapsed_seconds",
        "zone_id",
        "vehicle_object_id",
        "vehicle_class",
        "vehicle_speed_kmh",
        "vehicle_distance_to_zebra_m",
        "pedestrian_object_id",
        "pedestrian_speed_kmh",
        "pedestrian_distance_to_zebra_m",
        "vehicle_speed_trend",
        "approach_start_speed_kmh",
        "approach_end_speed_kmh",
        "approach_delta_kmh",
        "approach_samples",
        "rider_filtered_pedestrians_count",
    ]


def zebra_occupancy_fieldnames() -> List[str]:
    return [
        "frame_number",
        "elapsed_seconds",
        "zone_id",
        "objects_in_zone",
        "vehicles_in_zone",
        "pedestrians_in_zone",
        "bikes_in_zone",
        "class_counts_json",
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
        "is_rider",
        "associated_vehicle_id",
        "zebra_zone_id",
        "inside_zebra",
        "near_zebra",
        "distance_to_zebra_m",
        "inside_zebra_zone_ids",
        "near_zebra_zone_ids",
    ]


def build_analyzer(
    video_path: str,
    camera_id: str,
    camera_config: str,
    line_points: Optional[List[List[float]]] = None,
    zebra_points: Optional[List[List[float]]] = None,
    zebra_config: Optional[List[dict]] = None,
    pixels_per_meter: Optional[float] = None,
    zebra_speed_threshold_kmh: float = 15.0,
    zebra_zone_margin_m: float = 2.0,
    zebra_interaction_window_seconds: float = 3.0,
    zebra_speed_trend_deadband_kmh: float = 2.0,
    filter_riders_from_pedestrians: bool = True,
    max_riders_per_bike: int = 2,
    model_path: str = "yolov8l.pt",
    confidence: float = 0.25,
) -> TrafficMetricsAnalyzer:
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not Path(camera_config).exists():
        raise FileNotFoundError(f"Camera config not found: {camera_config}")
    profiles = build_camera_profile_map(camera_config)
    camera_profile = profiles.get(camera_id)
    if camera_profile is None:
        raise ValueError(f"No camera profile found for camera_id {camera_id!r} in {camera_config!r}.")
    counting_lines = build_counting_lines(camera_profile, line_points=line_points)
    zebra_zones = build_zebra_zones(camera_profile, zebra_points=zebra_points, zebra_config=zebra_config)
    return TrafficMetricsAnalyzer(
        camera_id=camera_id,
        camera_profile=camera_profile,
        detector=YoloTrackDetector(model_path=model_path, confidence=confidence),
        counting_lines=counting_lines,
        zebra_zones=zebra_zones,
        pixels_per_meter=pixels_per_meter,
        zebra_speed_threshold_kmh=zebra_speed_threshold_kmh,
        zebra_zone_margin_m=zebra_zone_margin_m,
        zebra_interaction_window_seconds=zebra_interaction_window_seconds,
        zebra_speed_trend_deadband_kmh=zebra_speed_trend_deadband_kmh,
        filter_riders_from_pedestrians=filter_riders_from_pedestrians,
        max_riders_per_bike=max_riders_per_bike,
    )


def parse_args(argv: Optional[Iterable[str]] = None):
    parser = argparse.ArgumentParser(description="Offline non-zebra traffic speed and count metrics")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a video and write traffic metrics")
    analyze_parser.add_argument("--video", required=True, help="Input video path")
    analyze_parser.add_argument("--camera-id", required=True, help="Camera ID from cameras.yaml")
    analyze_parser.add_argument("--camera-config", default="config/cameras.yaml", help="Camera configuration YAML")
    analyze_parser.add_argument("--output-dir", required=True, help="Directory for annotated video and metric outputs")
    analyze_parser.add_argument("--line-points", help="Optional counting line as JSON, e.g. '[[220,180],[220,360]]'")
    analyze_parser.add_argument("--line-config", help="Optional YAML created by setup-line")
    analyze_parser.add_argument("--zebra-points", help="Optional zebra polygon as JSON, e.g. '[[100,100],[300,100],[300,200],[100,200]]'")
    analyze_parser.add_argument("--zebra-config", help="Optional YAML created by setup-zebra")
    analyze_parser.add_argument("--zebra-speed-threshold", type=float, default=15.0, help="Vehicle speed threshold for zebra risk/violation")
    analyze_parser.add_argument("--zebra-zone-margin-m", type=float, default=2.0, help="Near-zone tolerance around zebra polygon in meters")
    analyze_parser.add_argument("--zebra-interaction-window-seconds", type=float, default=3.0, help="How long a pedestrian remains active near zebra")
    analyze_parser.add_argument("--zebra-speed-trend-deadband-kmh", type=float, default=2.0, help="Speed delta treated as constant when classifying zebra approach trend")
    analyze_parser.add_argument("--filter-riders-from-pedestrians", dest="filter_riders_from_pedestrians", action="store_true", default=True, help="Filter motorcycle/bicycle riders out of pedestrian zebra analysis")
    analyze_parser.add_argument("--disable-rider-filter", dest="filter_riders_from_pedestrians", action="store_false", help="Disable rider filtering for comparison/debugging")
    analyze_parser.add_argument("--max-riders-per-bike", type=int, default=2, help="Maximum pedestrian detections to associate with each motorcycle/bicycle")
    analyze_parser.add_argument("--pixels-per-meter", type=float, help="Optional speed calibration override")
    analyze_parser.add_argument("--model", default="yolov8l.pt", help="YOLO model path")
    analyze_parser.add_argument("--confidence", type=float, default=0.25, help="Detection confidence threshold")
    analyze_parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress output")

    setup_parser = subparsers.add_parser("setup-line", help="Click two points on the first frame and save a counting line YAML")
    setup_parser.add_argument("--video", required=True, help="Input video path")
    setup_parser.add_argument("--camera-id", required=True, help="Camera ID for the generated line YAML")
    setup_parser.add_argument("--output", required=True, help="Output line YAML path")
    setup_parser.add_argument("--line-id", default="", help="Line ID saved in the setup YAML")

    zebra_setup_parser = subparsers.add_parser("setup-zebra", help="Click a zebra polygon on the first frame and save YAML")
    zebra_setup_parser.add_argument("--video", required=True, help="Input video path")
    zebra_setup_parser.add_argument("--camera-id", required=True, help="Camera ID for the generated zebra YAML")
    zebra_setup_parser.add_argument("--output", required=True, help="Output zebra YAML path")
    zebra_setup_parser.add_argument("--zone-id", default="offline_zebra_crossing", help="Zebra zone ID saved in the setup YAML")
    zebra_setup_parser.add_argument("--multi", action="store_true", help="Click and save multiple zebra polygons into one YAML")

    parser.add_argument("--video", help=argparse.SUPPRESS)
    parser.add_argument("--camera-id", help=argparse.SUPPRESS)
    parser.add_argument("--camera-config", default="config/cameras.yaml", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", help=argparse.SUPPRESS)
    parser.add_argument("--line-points", help=argparse.SUPPRESS)
    parser.add_argument("--line-config", help=argparse.SUPPRESS)
    parser.add_argument("--zebra-points", help=argparse.SUPPRESS)
    parser.add_argument("--zebra-config", help=argparse.SUPPRESS)
    parser.add_argument("--zebra-speed-threshold", type=float, default=15.0, help=argparse.SUPPRESS)
    parser.add_argument("--zebra-zone-margin-m", type=float, default=2.0, help=argparse.SUPPRESS)
    parser.add_argument("--zebra-interaction-window-seconds", type=float, default=3.0, help=argparse.SUPPRESS)
    parser.add_argument("--zebra-speed-trend-deadband-kmh", type=float, default=2.0, help=argparse.SUPPRESS)
    parser.add_argument("--filter-riders-from-pedestrians", dest="filter_riders_from_pedestrians", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--disable-rider-filter", dest="filter_riders_from_pedestrians", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--max-riders-per-bike", type=int, default=2, help=argparse.SUPPRESS)
    parser.add_argument("--pixels-per-meter", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--model", default="yolov8l.pt", help=argparse.SUPPRESS)
    parser.add_argument("--confidence", type=float, default=0.25, help=argparse.SUPPRESS)
    parser.add_argument("--no-progress", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None):
    args = parse_args(argv)
    try:
        if args.command == "setup-line":
            setup_line_from_video(args)
            return
        if args.command == "setup-zebra":
            setup_zebra_from_video(args)
            return
        if args.command is None:
            required = ["video", "camera_id", "output_dir"]
            missing = [name.replace("_", "-") for name in required if not getattr(args, name, None)]
            if missing:
                raise SystemExit(f"Missing required arguments: {', '.join('--' + name for name in missing)}")
        line_points = _normalize_line_arg(args.line_points) if args.line_points else load_line_config(args.line_config)
        zebra_points = _normalize_polygon_arg(args.zebra_points)
        zebra_config = load_zebra_config(args.zebra_config)
        analyzer = build_analyzer(
            video_path=args.video,
            camera_id=args.camera_id,
            camera_config=args.camera_config,
            line_points=line_points,
            zebra_points=zebra_points,
            zebra_config=zebra_config,
            pixels_per_meter=args.pixels_per_meter,
            zebra_speed_threshold_kmh=args.zebra_speed_threshold,
            zebra_zone_margin_m=args.zebra_zone_margin_m,
            zebra_interaction_window_seconds=args.zebra_interaction_window_seconds,
            zebra_speed_trend_deadband_kmh=args.zebra_speed_trend_deadband_kmh,
            filter_riders_from_pedestrians=args.filter_riders_from_pedestrians,
            max_riders_per_bike=args.max_riders_per_bike,
            model_path=args.model,
            confidence=args.confidence,
        )
        summary = analyzer.analyze_video(args.video, args.output_dir, show_progress=not args.no_progress)
        print(json.dumps(summary["outputs"], indent=2))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Error: {exc}") from None


if __name__ == "__main__":
    main()
