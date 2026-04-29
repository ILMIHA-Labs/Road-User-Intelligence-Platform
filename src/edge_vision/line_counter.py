from math import hypot
from typing import Dict, List, Optional

from common.camera_config import DEFAULT_COUNTING_LINE_CLASSES
from common.event_schemas import CrossingEvent


class LineCrossingCounter:
    def __init__(self, counting_lines: Optional[List[dict]] = None, min_crossing_distance_px: float = 8.0):
        self.counting_lines = [line for line in (counting_lines or []) if line.get("enabled", True)]
        self.min_crossing_distance_px = float(min_crossing_distance_px)
        self.object_states: Dict[tuple, dict] = {}

    def process_tracks(self, camera_id: str, frame_number: int, tracks: List[dict], timestamp: str) -> List[CrossingEvent]:
        events: List[CrossingEvent] = []
        active_keys = set()

        for track in tracks:
            object_id = track["object_id"]
            class_name = track["class_name"]
            point = self._point_from_bbox(track["bbox"])

            for line in self.counting_lines:
                if class_name not in (line.get("classes") or DEFAULT_COUNTING_LINE_CLASSES):
                    continue

                state_key = (line["id"], object_id)
                active_keys.add(state_key)
                state = self.object_states.get(state_key, {})
                side_value = self._side_value(line["points"], point)
                current_distance = self._distance_to_line(line["points"], point)
                current_side = self._normalize_side(side_value, current_distance)

                previous_side = state.get("side")
                previous_distance = state.get("distance")
                emitted_direction = state.get("emitted_direction")

                if (
                    previous_side in (-1, 1)
                    and current_side in (-1, 1)
                    and previous_side != current_side
                    and max(current_distance, previous_distance or 0.0) >= self.min_crossing_distance_px
                ):
                    direction = "a_to_b" if previous_side > current_side else "b_to_a"
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

                state["side"] = current_side if current_side != 0 else previous_side
                state["distance"] = current_distance

                if current_side in (-1, 1) and current_distance >= self.min_crossing_distance_px * 1.5:
                    if emitted_direction == "a_to_b" and current_side < 0:
                        emitted_direction = None
                    elif emitted_direction == "b_to_a" and current_side > 0:
                        emitted_direction = None
                state["emitted_direction"] = emitted_direction
                self.object_states[state_key] = state

        stale_keys = [key for key in self.object_states.keys() if key not in active_keys]
        for key in stale_keys:
            del self.object_states[key]

        return events

    @staticmethod
    def _point_from_bbox(bbox: List[float]):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, y2)

    @staticmethod
    def _side_value(line_points: List[List[float]], point) -> float:
        (x1, y1), (x2, y2) = line_points
        px, py = point
        return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)

    def _normalize_side(self, value: float, distance: float) -> int:
        if distance <= self.min_crossing_distance_px:
            return 0
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    @staticmethod
    def _distance_to_line(line_points: List[List[float]], point) -> float:
        (x1, y1), (x2, y2) = line_points
        px, py = point
        denominator = hypot(x2 - x1, y2 - y1)
        if denominator == 0:
            return 0.0
        return abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / denominator
