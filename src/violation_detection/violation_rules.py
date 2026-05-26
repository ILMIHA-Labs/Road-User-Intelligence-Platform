import logging
from datetime import datetime, timezone

from common.event_schemas import ViolationEvent

logger = logging.getLogger(__name__)


def _distance(point_a, point_b):
    if (
        point_a is None
        or point_b is None
        or len(point_a) != 2
        or len(point_b) != 2
    ):
        return 0.0
    dx = float(point_a[0]) - float(point_b[0])
    dy = float(point_a[1]) - float(point_b[1])
    return (dx * dx + dy * dy) ** 0.5


def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _point_in_polygon(point, polygon):
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


class ViolationRulesEngine:
    """
    Evaluates business rules to detect safety violations based on object state.
    """
    def __init__(
        self,
        speed_limit_kmh=60.0,
        speed_tolerance_kmh=0.0,
        severe_speed_delta_kmh=20.0,
        speed_reset_delta_kmh=5.0,
        stopped_speed_threshold_kmh=3.0,
        stopped_duration_seconds=20,
        stopped_resume_speed_kmh=8.0,
        state_ttl_seconds=120,
        helmet_required_classes=None,
        helmet_violation_statuses=None,
        stopped_vehicle_classes=None,
        zones=None,
        stop_line_min_speed_kmh=5.0,
        stop_line_vehicle_classes=None,
        pedestrian_crossing_min_speed_kmh=5.0,
        pedestrian_crossing_window_seconds=2.0,
        crossing_min_presence_seconds=0.75,
        crossing_min_observations=2,
        crossing_vehicle_min_displacement_px=12.0,
        pedestrian_crossing_vehicle_classes=None,
        pedestrian_classes=None,
    ):
        self.speed_limit_kmh = speed_limit_kmh
        self.speed_tolerance_kmh = speed_tolerance_kmh
        self.severe_speed_delta_kmh = severe_speed_delta_kmh
        self.speed_reset_delta_kmh = speed_reset_delta_kmh
        self.stopped_speed_threshold_kmh = stopped_speed_threshold_kmh
        self.stopped_duration_seconds = stopped_duration_seconds
        self.stopped_resume_speed_kmh = stopped_resume_speed_kmh
        self.state_ttl_seconds = state_ttl_seconds
        self.helmet_required_classes = set(helmet_required_classes or {"motorcycle"})
        self.helmet_violation_statuses = set(
            helmet_violation_statuses or {"no_helmet", "missing_helmet"}
        )
        self.stopped_vehicle_classes = set(
            stopped_vehicle_classes or {"car", "bus", "truck"}
        )
        self.zones = zones or []
        self.stop_line_min_speed_kmh = stop_line_min_speed_kmh
        self.stop_line_vehicle_classes = set(
            stop_line_vehicle_classes or {"car", "bus", "truck", "motorcycle"}
        )
        self.pedestrian_crossing_min_speed_kmh = pedestrian_crossing_min_speed_kmh
        self.pedestrian_crossing_window_seconds = pedestrian_crossing_window_seconds
        self.crossing_min_presence_seconds = crossing_min_presence_seconds
        self.crossing_min_observations = crossing_min_observations
        self.crossing_vehicle_min_displacement_px = crossing_vehicle_min_displacement_px
        self.pedestrian_crossing_vehicle_classes = set(
            pedestrian_crossing_vehicle_classes or {"car", "bus", "truck", "motorcycle"}
        )
        self.pedestrian_classes = set(pedestrian_classes or {"pedestrian"})
        # A simple state cache: object_id -> dict of properties
        self.object_states = {}

    def _bbox_bottom_center(self, bbox):
        if len(bbox) != 4:
            return None
        x1, _, x2, y2 = bbox
        return [float((x1 + x2) / 2.0), float(y2)]

    def _matching_zones(self, category, point):
        if point is None:
            return []
        matches = []
        for zone in self.zones:
            if zone.get("category") != category:
                continue
            if _point_in_polygon(point, zone.get("points", [])):
                matches.append(zone)
        return matches

    def _zone_state_key(self, category, zone_id):
        return f"{category}:{zone_id}"

    def _update_zone_presence(self, state, point, timestamp):
        active_zone_ids = state.setdefault("active_zone_ids_by_category", {})
        zone_entered_at = state.setdefault("zone_entered_at", {})
        zone_observations = state.setdefault("zone_observations", {})

        for category in ("stop_line", "pedestrian_crossing", "zebra_crossing"):
            current_zone_ids = {
                zone.get("id")
                for zone in self._matching_zones(category, point)
                if zone.get("id")
            }
            previous_zone_ids = set(active_zone_ids.get(category, []))

            for zone_id in current_zone_ids:
                key = self._zone_state_key(category, zone_id)
                if zone_id not in previous_zone_ids:
                    zone_entered_at[key] = timestamp
                    zone_observations[key] = 1
                else:
                    zone_observations[key] = zone_observations.get(key, 1) + 1

            for zone_id in previous_zone_ids - current_zone_ids:
                key = self._zone_state_key(category, zone_id)
                zone_entered_at.pop(key, None)
                zone_observations.pop(key, None)

            active_zone_ids[category] = sorted(current_zone_ids)

    def _is_same_crossing_interaction(self, vehicle_state, pedestrian_state):
        vehicle_frame = vehicle_state.get("last_detection_frame_number")
        pedestrian_frame = pedestrian_state.get("last_detection_frame_number")
        if vehicle_frame is not None and pedestrian_frame is not None:
            return abs(int(vehicle_frame) - int(pedestrian_frame)) <= 1

        vehicle_time = _parse_timestamp(vehicle_state.get("last_detection_at"))
        pedestrian_time = _parse_timestamp(pedestrian_state.get("last_detection_at"))
        if vehicle_time is None or pedestrian_time is None:
            return False
        return vehicle_time == pedestrian_time

    def _crossing_matches(self, vehicle_object_id, category):
        vehicle_state = self.object_states.get(vehicle_object_id)
        if not vehicle_state:
            return []
        if vehicle_state.get("class") not in self.pedestrian_crossing_vehicle_classes:
            return []
        if vehicle_state.get("speed_kmh", 0.0) < self.pedestrian_crossing_min_speed_kmh:
            return []
        if vehicle_state.get("detection_observations", 0) < self.crossing_min_observations:
            return []
        if (
            vehicle_state.get("recent_motion_distance_px", 0.0)
            < self.crossing_vehicle_min_displacement_px
        ):
            return []

        vehicle_point = vehicle_state.get("anchor_point") or self._bbox_bottom_center(
            vehicle_state.get("bbox") or []
        )
        matching_vehicle_zones = self._matching_zones(category, vehicle_point)
        if not matching_vehicle_zones:
            return []

        zone_ids = {zone.get("id") for zone in matching_vehicle_zones}
        camera_id = vehicle_state.get("camera_id")
        active_matches = []
        for state in self.object_states.values():
            if state.get("class") not in self.pedestrian_classes:
                continue
            if state.get("camera_id") != camera_id:
                continue
            if state.get("detection_observations", 0) < self.crossing_min_observations:
                continue
            if not self._is_same_crossing_interaction(vehicle_state, state):
                continue
            pedestrian_point = state.get("anchor_point") or self._bbox_bottom_center(
                state.get("bbox") or []
            )
            crossing_zones = self._matching_zones(category, pedestrian_point)
            for zone in crossing_zones:
                zone_id = zone.get("id")
                if zone_id not in zone_ids:
                    continue
                pedestrian_time = _parse_timestamp(state.get("last_detection_at"))
                entered_at = _parse_timestamp(
                    state.get("zone_entered_at", {}).get(
                        self._zone_state_key(category, zone_id)
                    )
                )
                dwell_seconds = 0.0
                if entered_at is not None and pedestrian_time is not None:
                    dwell_seconds = (pedestrian_time - entered_at).total_seconds()
                if (
                    dwell_seconds >= self.crossing_min_presence_seconds
                    and state.get("zone_observations", {}).get(
                        self._zone_state_key(category, zone_id), 0
                    )
                    >= self.crossing_min_observations
                ):
                    active_matches.append(zone)
                    break
        return active_matches

    def _pedestrian_crossing_matches(self, vehicle_object_id):
        return self._crossing_matches(vehicle_object_id, "pedestrian_crossing")

    def _zebra_crossing_matches(self, vehicle_object_id):
        return self._crossing_matches(vehicle_object_id, "zebra_crossing")

    def get_related_object_ids(self, object_id):
        state = self.object_states.get(object_id)
        if not state:
            return [object_id]

        related_ids = {object_id}
        if state.get("class") == "pedestrian":
            for candidate_id, candidate_state in self.object_states.items():
                if candidate_state.get("class") not in self.pedestrian_crossing_vehicle_classes:
                    continue
                if candidate_state.get("camera_id") != state.get("camera_id"):
                    continue
                if self._pedestrian_crossing_matches(candidate_id) or self._zebra_crossing_matches(candidate_id):
                    related_ids.add(candidate_id)
        return list(related_ids)

    def cleanup_stale_states(self, now=None):
        if not self.state_ttl_seconds:
            return

        now = now or datetime.now(timezone.utc)
        stale_ids = []
        for object_id, state in self.object_states.items():
            last_seen = _parse_timestamp(state.get("last_seen"))
            if last_seen is None:
                continue
            age_seconds = (now - last_seen).total_seconds()
            if age_seconds > self.state_ttl_seconds:
                stale_ids.append(object_id)

        for object_id in stale_ids:
            del self.object_states[object_id]

    def update_state(self, object_id, detection_event=None, speed_event=None):
        """
        Updates the cached state of an object using incoming MQTT events.
        """
        event_time = None
        if detection_event:
            event_time = detection_event.get("timestamp")
        elif speed_event:
            event_time = speed_event.get("timestamp")

        self.cleanup_stale_states(now=_parse_timestamp(event_time) or datetime.now(timezone.utc))

        if object_id not in self.object_states:
             self.object_states[object_id] = {
                 "class": "unknown", 
                 "helmet_status": "unknown", 
                 "speed_kmh": 0.0,
                 "bbox": [],
                 "last_seen": "",
                 "last_detection_at": None,
                 "last_detection_frame_number": None,
                 "camera_id": "unknown",
                 "speed_violation_triggered": False,
                 "severe_speed_violation_triggered": False,
                 "helmet_violation_triggered": False,
                 "stopped_since": None,
                 "stopped_vehicle_violation_triggered": False,
                 "stopped_vehicle_zone_id": None,
                 "stop_line_violation_triggered": False,
                 "pedestrian_crossing_violation_triggered": False,
                 "zebra_crossing_violation_triggered": False,
                 "detection_observations": 0,
                 "anchor_point": None,
                 "previous_anchor_point": None,
                 "recent_motion_distance_px": 0.0,
                 "active_zone_ids_by_category": {},
                 "zone_entered_at": {},
                 "zone_observations": {},
             }
             
        state = self.object_states[object_id]
        
        if detection_event:
            state["class"] = detection_event.get("class", state["class"])
            state["helmet_status"] = detection_event.get("helmet_status", state["helmet_status"])
            state["bbox"] = detection_event.get("bbox", state["bbox"])
            state["last_seen"] = detection_event.get("timestamp", state["last_seen"])
            state["last_detection_at"] = detection_event.get(
                "timestamp", state["last_detection_at"]
            )
            state["last_detection_frame_number"] = detection_event.get(
                "frame_number", state["last_detection_frame_number"]
            )
            # Required for multi-camera deduplication later on in MVP
            state["camera_id"] = detection_event.get("camera_id")
            state["detection_observations"] = state.get("detection_observations", 0) + 1
            anchor_point = self._bbox_bottom_center(state.get("bbox") or [])
            previous_anchor_point = state.get("anchor_point")
            state["previous_anchor_point"] = previous_anchor_point
            state["anchor_point"] = anchor_point
            state["recent_motion_distance_px"] = _distance(
                previous_anchor_point, anchor_point
            )
            event_timestamp = detection_event.get("timestamp", state["last_seen"])
            if anchor_point is not None:
                self._update_zone_presence(state, anchor_point, event_timestamp)

        if speed_event:
            state["speed_kmh"] = speed_event.get("speed_kmh", state["speed_kmh"])
            state["last_seen"] = speed_event.get("timestamp", state["last_seen"])

    def evaluate_violations(self, object_id):
        """
        Checks all rules against the updated state of an object and returns a list of violation types.
        """
        if object_id not in self.object_states:
            return []
            
        state = self.object_states[object_id]
        violations = []

        # Rule 1: Speed Violation
        speed_threshold = self.speed_limit_kmh + self.speed_tolerance_kmh
        speed_reset_threshold = max(0.0, speed_threshold - self.speed_reset_delta_kmh)
        current_speed = state.get("speed_kmh", 0.0)

        # Reset speed-related state once the object clearly falls back below the threshold.
        if current_speed <= speed_reset_threshold:
            state["speed_violation_triggered"] = False
            state["severe_speed_violation_triggered"] = False

        if current_speed > speed_threshold + self.severe_speed_delta_kmh:
            if not state.get("severe_speed_violation_triggered", False) and not state.get(
                "speed_violation_triggered", False
            ):
                violations.append("severe_speed_violation")
                state["severe_speed_violation_triggered"] = True
                state["speed_violation_triggered"] = True
        elif current_speed > speed_threshold:
            if not state.get("speed_violation_triggered", False):
                violations.append("speed_violation")
                state["speed_violation_triggered"] = True

        # Rule 2: Helmet Violation
        # In a real scenario, "no_helmet" would be set by a secondary classification model
        # inside the edge node if a motorcycle is detected.
        requires_helmet = state["class"] in self.helmet_required_classes
        helmet_status = state.get("helmet_status", "unknown")
        if not requires_helmet or helmet_status == "helmet":
            state["helmet_violation_triggered"] = False

        if requires_helmet and helmet_status in self.helmet_violation_statuses:
            if not state.get("helmet_violation_triggered", False):
                 violations.append("helmet_violation")
                 state["helmet_violation_triggered"] = True

        # Rule 3: Stopped Vehicle Violation
        applicable_stopped_class = state["class"] in self.stopped_vehicle_classes
        current_time = _parse_timestamp(state.get("last_seen")) or datetime.now(timezone.utc)

        zebra_zone_matches = self._matching_zones(
            "zebra_crossing",
            state.get("anchor_point") or self._bbox_bottom_center(state.get("bbox") or []),
        )

        if (
            applicable_stopped_class
            and self.stopped_duration_seconds > 0
            and current_speed <= self.stopped_speed_threshold_kmh
            and zebra_zone_matches
        ):
            if state.get("stopped_since") is None:
                state["stopped_since"] = state.get("last_seen")

            stopped_since = _parse_timestamp(state.get("stopped_since"))
            if stopped_since is not None:
                stopped_seconds = (current_time - stopped_since).total_seconds()
                if (
                    stopped_seconds >= self.stopped_duration_seconds
                    and not state.get("stopped_vehicle_violation_triggered", False)
                ):
                    violations.append("stopped_vehicle_violation")
                    state["stopped_vehicle_violation_triggered"] = True
                    state["stopped_vehicle_zone_id"] = zebra_zone_matches[0].get("id")
        elif (not applicable_stopped_class) or current_speed >= self.stopped_resume_speed_kmh:
            state["stopped_since"] = None
            state["stopped_vehicle_violation_triggered"] = False
            state["stopped_vehicle_zone_id"] = None
        elif not zebra_zone_matches:
            state["stopped_since"] = None
            state["stopped_vehicle_violation_triggered"] = False
            state["stopped_vehicle_zone_id"] = None

        # Rule 4: Stop Line Violation
        stop_line_matches = []
        if state["class"] in self.stop_line_vehicle_classes and current_speed >= self.stop_line_min_speed_kmh:
            anchor_point = self._bbox_bottom_center(state.get("bbox") or [])
            stop_line_matches = self._matching_zones("stop_line", anchor_point)

        if stop_line_matches:
            if not state.get("stop_line_violation_triggered", False):
                violations.append("stop_line_violation")
                state["stop_line_violation_triggered"] = True
                state["stop_line_zone_id"] = stop_line_matches[0].get("id")
        else:
            state["stop_line_violation_triggered"] = False
            state["stop_line_zone_id"] = None

        # Rule 5: Pedestrian Crossing Violation
        crossing_matches = self._pedestrian_crossing_matches(object_id)
        if crossing_matches:
            if not state.get("pedestrian_crossing_violation_triggered", False):
                violations.append("pedestrian_crossing_violation")
                state["pedestrian_crossing_violation_triggered"] = True
                state["pedestrian_crossing_zone_id"] = crossing_matches[0].get("id")
        else:
            state["pedestrian_crossing_violation_triggered"] = False
            state["pedestrian_crossing_zone_id"] = None

        # Rule 6: Zebra Crossing Violation
        zebra_matches = self._zebra_crossing_matches(object_id)
        if zebra_matches:
            if not state.get("zebra_crossing_violation_triggered", False):
                violations.append("zebra_crossing_violation")
                state["zebra_crossing_violation_triggered"] = True
                state["zebra_crossing_zone_id"] = zebra_matches[0].get("id")
        else:
            state["zebra_crossing_violation_triggered"] = False
            state["zebra_crossing_zone_id"] = None
        
        return violations
        
    def generate_violation_events(self, object_id):
        """
        Evaluates rules and packages them into the required JSON schema.
        """
        violation_types = self.evaluate_violations(object_id)
        events = []
        
        state = self.object_states.get(object_id)
        if not state or not violation_types:
            return events

        for vtype in violation_types:
             events.append(
                 ViolationEvent(
                     violation_type=vtype,
                     object_id=object_id,
                     camera_id=state.get("camera_id", "unknown"),
                     timestamp=state.get("last_seen", ""),
                 )
             )
             
        return events
