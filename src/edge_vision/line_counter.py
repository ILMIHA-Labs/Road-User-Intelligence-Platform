from math import hypot
from typing import Dict, List, Optional, Tuple

from common.camera_config import DEFAULT_COUNTING_LINE_CLASSES
from common.event_schemas import CrossingEvent


class LineCrossingCounter:
    def __init__(self, counting_lines: Optional[List[dict]] = None, min_crossing_distance_px: float = 8.0):
        self.counting_lines = [self._normalize_line(line, min_crossing_distance_px) for line in (counting_lines or []) if line.get("enabled", True)]
        self.object_states: Dict[tuple, dict] = {}

    def process_tracks(self, camera_id: str, frame_number: int, tracks: List[dict], timestamp: str) -> List[CrossingEvent]:
        events: List[CrossingEvent] = []
        active_keys = set()

        for track in tracks:
            object_id = track["object_id"]
            class_name = self._canonical_class_name(track["class_name"])
            anchor_points = self._anchor_points_from_bbox(track["bbox"])

            for line in self.counting_lines:
                if class_name not in line["classes"]:
                    continue

                state_key = (line["id"], object_id)
                active_keys.add(state_key)
                state = self.object_states.get(
                    state_key,
                    {
                        "observations": 0,
                        "last_point": None,
                        "last_side": None,
                        "last_distance": None,
                        "emitted_direction": None,
                    },
                )

                point = anchor_points["bottom_center"]
                side_value = self._side_value(line["points"], point)
                current_distance = self._distance_to_line(line["points"], point)
                current_side = self._normalize_side(side_value, current_distance, line["min_crossing_distance_px"])
                previous_anchor_points = state.get("last_anchor_points") or {}
                previous_side = state.get("last_side")
                previous_observations = state.get("observations", 0)
                emitted_direction = state.get("emitted_direction")

                crossed_segment = False
                direction = None
                for anchor_name, anchor_point in anchor_points.items():
                    previous_anchor_point = previous_anchor_points.get(anchor_name)
                    candidate = self._crossing_candidate(
                        previous_anchor_point,
                        anchor_point,
                        line,
                        min_observations=previous_observations,
                    )
                    if candidate:
                        crossed_segment = True
                        direction = candidate
                        break

                if crossed_segment:
                    if emitted_direction != direction:
                        events.append(
                            CrossingEvent(
                                camera_id=camera_id,
                                line_id=line["id"],
                                line_label=line["label"],
                                object_id=object_id,
                                class_name=class_name,
                                direction=direction,
                                timestamp=timestamp,
                                frame_number=frame_number,
                                source="edge",
                            )
                        )
                        emitted_direction = direction

                if current_side in (-1, 1) and current_distance >= line["reset_distance_px"]:
                    if emitted_direction == "a_to_b" and current_side < 0:
                        emitted_direction = None
                    elif emitted_direction == "b_to_a" and current_side > 0:
                        emitted_direction = None

                state["observations"] = previous_observations + 1
                state["last_point"] = point
                state["last_anchor_points"] = anchor_points
                state["last_side"] = current_side if current_side != 0 else previous_side
                state["last_distance"] = current_distance
                state["emitted_direction"] = emitted_direction
                self.object_states[state_key] = state

        stale_keys = [key for key in self.object_states.keys() if key not in active_keys]
        for key in stale_keys:
            del self.object_states[key]

        return events

    @staticmethod
    def _normalize_line(line: dict, fallback_distance_px: float) -> dict:
        min_distance = float(line.get("min_crossing_distance_px", fallback_distance_px))
        reset_distance = float(line.get("reset_distance_px", max(min_distance * 1.5, min_distance + 4.0)))
        min_displacement = float(line.get("min_displacement_px", max(min_distance * 1.5, min_distance + 4.0)))
        min_observations = max(2, int(line.get("min_observations", 2)))
        line_window_margin = float(line.get("line_window_margin_px", max(18.0, min_distance * 2.0)))
        classes = [LineCrossingCounter._canonical_class_name(value) for value in (line.get("classes") or DEFAULT_COUNTING_LINE_CLASSES)]
        return {
            **line,
            "classes": [value for value in classes if value],
            "min_crossing_distance_px": min_distance,
            "reset_distance_px": reset_distance,
            "min_displacement_px": min_displacement,
            "min_observations": min_observations,
            "line_window_margin_px": line_window_margin,
        }

    @staticmethod
    def _canonical_class_name(value: Optional[str]) -> str:
        if not value:
            return ""
        return "pedestrian" if value == "person" else value

    @staticmethod
    def _point_from_bbox(bbox: List[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, y2)

    @staticmethod
    def _anchor_points_from_bbox(bbox: List[float]) -> Dict[str, Tuple[float, float]]:
        x1, y1, x2, y2 = bbox
        return {
            "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            "bottom_center": ((x1 + x2) / 2.0, y2),
        }

    @staticmethod
    def _side_value(line_points: List[List[float]], point: Tuple[float, float]) -> float:
        (x1, y1), (x2, y2) = line_points
        px, py = point
        return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)

    @staticmethod
    def _normalize_side(value: float, distance: float, min_crossing_distance_px: float) -> int:
        if distance <= min_crossing_distance_px:
            return 0
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    @staticmethod
    def _distance_to_line(line_points: List[List[float]], point: Tuple[float, float]) -> float:
        (x1, y1), (x2, y2) = line_points
        px, py = point
        denominator = hypot(x2 - x1, y2 - y1)
        if denominator == 0:
            return 0.0
        return abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / denominator

    @staticmethod
    def _crossing_candidate(previous_point: Optional[Tuple[float, float]], current_point: Tuple[float, float], line: dict, min_observations: int) -> Optional[str]:
        if previous_point is None or min_observations < line["min_observations"]:
            return None

        displacement = hypot(current_point[0] - previous_point[0], current_point[1] - previous_point[1])
        if displacement < line["min_displacement_px"]:
            return None

        previous_side_value = LineCrossingCounter._side_value(line["points"], previous_point)
        current_side_value = LineCrossingCounter._side_value(line["points"], current_point)
        if previous_side_value == 0 or current_side_value == 0:
            return None
        elif (previous_side_value > 0) == (current_side_value > 0):
            return None

        if not LineCrossingCounter._motion_intersects_line_window(
            previous_point,
            current_point,
            line["points"][0],
            line["points"][1],
            margin_px=line["line_window_margin_px"],
        ):
            return None

        return "a_to_b" if previous_side_value > current_side_value else "b_to_a"

    @staticmethod
    def _motion_intersects_line_window(
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        q1: List[float],
        q2: List[float],
        margin_px: float,
    ) -> bool:
        if LineCrossingCounter._segments_intersect(p1, p2, q1, q2):
            return True

        px, py = p1
        rx, ry = p2[0] - p1[0], p2[1] - p1[1]
        qx, qy = q1
        sx, sy = q2[0] - q1[0], q2[1] - q1[1]
        denominator = rx * sy - ry * sx
        if abs(denominator) <= 1e-9:
            return False

        qmpx, qmpy = qx - px, qy - py
        t = (qmpx * sy - qmpy * sx) / denominator
        u = (qmpx * ry - qmpy * rx) / denominator
        line_length = max(hypot(sx, sy), 1.0)
        margin_ratio = margin_px / line_length
        return 0.0 <= t <= 1.0 and -margin_ratio <= u <= 1.0 + margin_ratio

    @staticmethod
    def _segments_intersect(p1: Tuple[float, float], p2: Tuple[float, float], q1: List[float], q2: List[float]) -> bool:
        def orientation(a, b, c):
            value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
            if abs(value) <= 1e-9:
                return 0
            return 1 if value > 0 else 2

        def on_segment(a, b, c):
            return (
                min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
                and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
            )

        o1 = orientation(p1, p2, q1)
        o2 = orientation(p1, p2, q2)
        o3 = orientation(q1, q2, p1)
        o4 = orientation(q1, q2, p2)

        if o1 != o2 and o3 != o4:
            return True

        if o1 == 0 and on_segment(p1, q1, p2):
            return True
        if o2 == 0 and on_segment(p1, q2, p2):
            return True
        if o3 == 0 and on_segment(q1, p1, q2):
            return True
        if o4 == 0 and on_segment(q1, p2, q2):
            return True
        return False
