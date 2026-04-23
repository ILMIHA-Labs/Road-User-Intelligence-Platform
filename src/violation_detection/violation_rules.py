import logging
from datetime import datetime, timezone

from common.event_schemas import ViolationEvent

logger = logging.getLogger(__name__)


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
        max_motorcycle_riders=2,
        rider_association_window_seconds=2,
        rider_horizontal_margin_ratio=0.35,
        rider_upper_margin_ratio=0.75,
        rider_lower_margin_ratio=0.25,
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
        self.max_motorcycle_riders = max_motorcycle_riders
        self.rider_association_window_seconds = rider_association_window_seconds
        self.rider_horizontal_margin_ratio = rider_horizontal_margin_ratio
        self.rider_upper_margin_ratio = rider_upper_margin_ratio
        self.rider_lower_margin_ratio = rider_lower_margin_ratio
        # A simple state cache: object_id -> dict of properties
        self.object_states = {}

    def _is_recent_pair(self, state_a, state_b):
        ts_a = _parse_timestamp(state_a.get("last_seen"))
        ts_b = _parse_timestamp(state_b.get("last_seen"))
        if ts_a is None or ts_b is None:
            return False
        return abs((ts_a - ts_b).total_seconds()) <= self.rider_association_window_seconds

    def _is_pedestrian_on_motorcycle(self, motorcycle_state, pedestrian_state):
        mbox = motorcycle_state.get("bbox") or []
        pbox = pedestrian_state.get("bbox") or []
        if len(mbox) != 4 or len(pbox) != 4:
            return False

        mx1, my1, mx2, my2 = mbox
        px1, py1, px2, py2 = pbox
        mwidth = max(mx2 - mx1, 1.0)
        mheight = max(my2 - my1, 1.0)
        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0

        within_x = (mx1 - mwidth * self.rider_horizontal_margin_ratio) <= pcx <= (
            mx2 + mwidth * self.rider_horizontal_margin_ratio
        )
        within_y = (my1 - mheight * self.rider_upper_margin_ratio) <= pcy <= (
            my2 + mheight * self.rider_lower_margin_ratio
        )
        return within_x and within_y

    def _association_score(self, motorcycle_state, pedestrian_state):
        if not self._is_recent_pair(motorcycle_state, pedestrian_state):
            return None
        if not self._is_pedestrian_on_motorcycle(motorcycle_state, pedestrian_state):
            return None

        mbox = motorcycle_state.get("bbox") or []
        pbox = pedestrian_state.get("bbox") or []
        if len(mbox) != 4 or len(pbox) != 4:
            return None

        mx1, my1, mx2, my2 = mbox
        px1, py1, px2, py2 = pbox
        mwidth = max(mx2 - mx1, 1.0)
        mheight = max(my2 - my1, 1.0)
        mcx = (mx1 + mx2) / 2.0
        mcy = (my1 + my2) / 2.0
        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0

        horizontal_offset = abs(pcx - mcx) / mwidth
        vertical_offset = abs(pcy - mcy) / mheight
        return horizontal_offset + vertical_offset

    def _best_motorcycle_match(self, pedestrian_object_id):
        pedestrian_state = self.object_states.get(pedestrian_object_id)
        if not pedestrian_state or pedestrian_state.get("class") != "pedestrian":
            return None

        camera_id = pedestrian_state.get("camera_id")
        best_match_id = None
        best_score = None
        for object_id, state in self.object_states.items():
            if state.get("class") != "motorcycle":
                continue
            if state.get("camera_id") != camera_id:
                continue
            score = self._association_score(state, pedestrian_state)
            if score is None:
                continue
            if best_score is None or score < best_score:
                best_score = score
                best_match_id = object_id
        return best_match_id

    def _count_motorcycle_riders(self, motorcycle_object_id):
        motorcycle_state = self.object_states.get(motorcycle_object_id)
        if not motorcycle_state or motorcycle_state.get("class") != "motorcycle":
            return 0

        camera_id = motorcycle_state.get("camera_id")
        rider_count = 1  # driver/rider on the motorcycle itself
        for object_id, state in self.object_states.items():
            if object_id == motorcycle_object_id:
                continue
            if state.get("class") != "pedestrian":
                continue
            if state.get("camera_id") != camera_id:
                continue
            if self._best_motorcycle_match(object_id) == motorcycle_object_id:
                rider_count += 1
        return rider_count

    def get_related_object_ids(self, object_id):
        state = self.object_states.get(object_id)
        if not state:
            return [object_id]

        related_ids = {object_id}
        if state.get("class") == "pedestrian":
            best_match_id = self._best_motorcycle_match(object_id)
            if best_match_id is not None:
                related_ids.add(best_match_id)
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
                 "camera_id": "unknown",
                 "speed_violation_triggered": False,
                 "severe_speed_violation_triggered": False,
                 "helmet_violation_triggered": False,
                 "stopped_since": None,
                 "stopped_vehicle_violation_triggered": False,
                 "multiple_riders_violation_triggered": False,
             }
             
        state = self.object_states[object_id]
        
        if detection_event:
            state["class"] = detection_event.get("class", state["class"])
            state["helmet_status"] = detection_event.get("helmet_status", state["helmet_status"])
            state["bbox"] = detection_event.get("bbox", state["bbox"])
            state["last_seen"] = detection_event.get("timestamp", state["last_seen"])
            # Required for multi-camera deduplication later on in MVP
            state["camera_id"] = detection_event.get("camera_id")

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

        # Rule 3: Too many riders on a motorcycle
        if state["class"] == "motorcycle" and self.max_motorcycle_riders > 0:
            rider_count = self._count_motorcycle_riders(object_id)
            state["estimated_rider_count"] = rider_count
            if rider_count <= self.max_motorcycle_riders:
                state["multiple_riders_violation_triggered"] = False
            elif not state.get("multiple_riders_violation_triggered", False):
                violations.append("multiple_riders_violation")
                state["multiple_riders_violation_triggered"] = True

        # Rule 4: Stopped Vehicle Violation
        applicable_stopped_class = state["class"] in self.stopped_vehicle_classes
        current_time = _parse_timestamp(state.get("last_seen")) or datetime.now(timezone.utc)

        if (
            applicable_stopped_class
            and self.stopped_duration_seconds > 0
            and current_speed <= self.stopped_speed_threshold_kmh
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
        elif (not applicable_stopped_class) or current_speed >= self.stopped_resume_speed_kmh:
            state["stopped_since"] = None
            state["stopped_vehicle_violation_triggered"] = False

        # Rule 5: Zebra Crossing Violation (MVP simple stub)
        # We would ideally check if a pedestrian is in a designated polygonal zone, 
        # and if a fast-moving vehicle intersects the pedestrian's path. We'll leave it as a stub for MVP.
        
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
