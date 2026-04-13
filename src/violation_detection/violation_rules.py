import logging
from common.event_schemas import ViolationEvent

logger = logging.getLogger(__name__)

class ViolationRulesEngine:
    """
    Evaluates business rules to detect safety violations based on object state.
    """
    def __init__(self, speed_limit_kmh=60.0):
        self.speed_limit_kmh = speed_limit_kmh
        # A simple state cache: object_id -> dict of properties
        self.object_states = {}

    def update_state(self, object_id, detection_event=None, speed_event=None):
        """
        Updates the cached state of an object using incoming MQTT events.
        """
        if object_id not in self.object_states:
             self.object_states[object_id] = {
                 "class": "unknown", 
                 "helmet_status": "unknown", 
                 "speed_kmh": 0.0,
                 "bbox": [],
                 "last_seen": ""
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
        if state["speed_kmh"] > self.speed_limit_kmh:
             # Basic check to avoid continuous alerts for the same object
             if not state.get("speed_violation_triggered", False):
                 violations.append("speed_violation")
                 state["speed_violation_triggered"] = True

        # Rule 2: Helmet Violation
        # In a real scenario, "no_helmet" would be set by a secondary classification model 
        # inside the edge node if a motorcycle is detected.
        if state["class"] == "motorcycle" and state["helmet_status"] == "no_helmet":
            if not state.get("helmet_violation_triggered", False):
                 violations.append("helmet_violation")
                 state["helmet_violation_triggered"] = True
                 
        # Rule 3: Zebra Crossing Violation (MVP simple stub)
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
