"""Derived crossing-safety research measures.

Consumes the per-frame track rows produced by
``TrafficMetricsAnalyzer.analyze_frame`` (each carrying ``_zebra_zone_states``
with per-zone ``near``/``inside``/``distance_m``) and maintains three state
machines that yield standard road-safety research outputs:

- pedestrian crossing episodes (kerb wait time + crossing duration)
- driver yielding opportunities and the aggregate yielding rate
- post-encroachment time (PET) between sequential zone occupancies

All outputs are event-level rows suitable for CSV export plus an aggregate
summary block for the metrics JSON. PET events are only emitted for strictly
sequential occupancies; simultaneous vehicle/pedestrian presence is already
covered by ``zebra_crossing_violation`` events.
"""
from statistics import median
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from common.constants import (
    PEDESTRIAN_WAITING_SPEED_KMH,
    PET_CRITICAL_SECONDS,
    PET_WINDOW_SECONDS,
    YIELD_SPEED_THRESHOLD_KMH,
)


def _round_opt(value: Optional[float], digits: int = 3) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _percentile(sorted_values: List[float], ratio: float) -> Optional[float]:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * ratio)))
    return sorted_values[index]


class SafetyMeasuresTracker:
    """Tracks crossing-safety measures across frames for one analysis run."""

    def __init__(
        self,
        camera_id: str,
        vehicle_classes: FrozenSet[str],
        pedestrian_classes: FrozenSet[str],
        stale_after_seconds: float = 3.0,
        waiting_speed_kmh: float = PEDESTRIAN_WAITING_SPEED_KMH,
        yield_speed_kmh: float = YIELD_SPEED_THRESHOLD_KMH,
        approach_min_speed_kmh: float = 15.0,
        pet_window_seconds: float = PET_WINDOW_SECONDS,
        pet_critical_seconds: float = PET_CRITICAL_SECONDS,
    ) -> None:
        self.camera_id = camera_id
        self.vehicle_classes = vehicle_classes
        self.pedestrian_classes = pedestrian_classes
        self.stale_after_seconds = float(stale_after_seconds)
        self.waiting_speed_kmh = float(waiting_speed_kmh)
        self.yield_speed_kmh = float(yield_speed_kmh)
        self.approach_min_speed_kmh = float(approach_min_speed_kmh)
        self.pet_window_seconds = float(pet_window_seconds)
        self.pet_critical_seconds = float(pet_critical_seconds)

        # Output rows
        self.pedestrian_episode_rows: List[dict] = []
        self.yielding_event_rows: List[dict] = []
        self.pet_event_rows: List[dict] = []

        # object_id -> "pedestrian"/"vehicle" and object_id -> class name,
        # populated on every frame so exit-category (PET) and yielding
        # vehicle_class lookups resolve even after the object leaves frame.
        self._object_categories: Dict[int, str] = {}
        self._object_classes: Dict[int, str] = {}

        # Pedestrian episode state, keyed by (pedestrian_id, zone_id)
        self._ped_states: Dict[Tuple[int, str], dict] = {}
        # Yielding opportunity state, keyed by (vehicle_id, zone_id)
        self._yield_states: Dict[Tuple[int, str], dict] = {}
        # Zone occupancy per object, keyed by (object_id, zone_id) -> entry time
        self._inside_since: Dict[Tuple[int, str], float] = {}
        # Most recent zone exit per (zone_id, category) -> (exit_time, object_id)
        self._last_exit: Dict[Tuple[str, str], Tuple[float, int]] = {}
        self._pet_keys: Set[Tuple[str, int, int, str]] = set()

    # ------------------------------------------------------------------
    # Frame ingestion
    # ------------------------------------------------------------------

    def update(self, elapsed_seconds: float, frame_rows: List[dict]) -> None:
        pedestrians = [
            row for row in frame_rows
            if row.get("class") in self.pedestrian_classes and not row.get("is_rider")
        ]
        vehicles = [row for row in frame_rows if row.get("class") in self.vehicle_classes]

        for row in pedestrians:
            self._object_categories[int(row["object_id"])] = "pedestrian"
            self._object_classes[int(row["object_id"])] = str(row.get("class"))
        for row in vehicles:
            self._object_categories[int(row["object_id"])] = "vehicle"
            self._object_classes[int(row["object_id"])] = str(row.get("class"))

        self._update_pedestrian_episodes(elapsed_seconds, pedestrians)
        self._update_occupancy_and_pet(elapsed_seconds, pedestrians, vehicles)
        self._update_yielding(elapsed_seconds, vehicles)
        self._expire_stale(elapsed_seconds)

    def finalize(self, elapsed_seconds: float) -> None:
        """Close any open state at end of video."""
        for key in list(self._ped_states):
            self._close_ped_episode(key, elapsed_seconds, outcome="lost")
        for key in list(self._yield_states):
            self._resolve_yield(key, elapsed_seconds, entered_zone=False, lost=True)

    # ------------------------------------------------------------------
    # Pedestrian crossing episodes
    # ------------------------------------------------------------------

    def _update_pedestrian_episodes(self, now: float, pedestrians: List[dict]) -> None:
        for row in pedestrians:
            speed = row.get("speed_kmh")
            for state in row.get("_zebra_zone_states", []):
                zone_id = state.get("zone_id")
                if not zone_id:
                    continue
                key = (int(row["object_id"]), str(zone_id))
                ped = self._ped_states.get(key)
                if state.get("inside"):
                    if ped is None:
                        # Entered without an observed wait (e.g. first seen inside).
                        ped = {"wait_start": None, "cross_start": now, "phase": "crossing"}
                        self._ped_states[key] = ped
                    elif ped["phase"] == "waiting":
                        ped["cross_start"] = now
                        ped["phase"] = "crossing"
                    ped["last_seen"] = now
                    ped["last_inside"] = now
                elif state.get("near"):
                    if ped is None:
                        if speed is not None and float(speed) <= self.waiting_speed_kmh:
                            self._ped_states[key] = {
                                "wait_start": now,
                                "cross_start": None,
                                "phase": "waiting",
                                "last_seen": now,
                            }
                    else:
                        if ped["phase"] == "crossing":
                            # Left the zone onto the far side: episode complete.
                            self._close_ped_episode(key, now, outcome="crossed")
                        else:
                            ped["last_seen"] = now

    def _close_ped_episode(self, key: Tuple[int, str], now: float, outcome: str) -> None:
        ped = self._ped_states.pop(key, None)
        if ped is None or ped.get("cross_start") is None:
            # Waiting-only state that never crossed: dropped, not emitted.
            return
        pedestrian_id, zone_id = key
        cross_start = float(ped["cross_start"])
        cross_end = float(ped.get("last_inside", now))
        wait_start = ped.get("wait_start")
        self.pedestrian_episode_rows.append(
            {
                "camera_id": self.camera_id,
                "zone_id": zone_id,
                "pedestrian_object_id": pedestrian_id,
                "wait_start_seconds": _round_opt(wait_start),
                "crossing_start_seconds": round(cross_start, 3),
                "crossing_end_seconds": round(cross_end, 3),
                "wait_seconds": _round_opt(cross_start - wait_start if wait_start is not None else None),
                "crossing_seconds": round(max(0.0, cross_end - cross_start), 3),
                "outcome": outcome,
            }
        )

    # ------------------------------------------------------------------
    # Zone occupancy transitions + PET
    # ------------------------------------------------------------------

    def _update_occupancy_and_pet(self, now: float, pedestrians: List[dict], vehicles: List[dict]) -> None:
        seen_inside: Set[Tuple[int, str]] = set()
        for category, rows in (("pedestrian", pedestrians), ("vehicle", vehicles)):
            for row in rows:
                object_id = int(row["object_id"])
                for state in row.get("_zebra_zone_states", []):
                    zone_id = state.get("zone_id")
                    if not zone_id or not state.get("inside"):
                        continue
                    occ_key = (object_id, str(zone_id))
                    seen_inside.add(occ_key)
                    if occ_key not in self._inside_since:
                        self._inside_since[occ_key] = now
                        self._maybe_emit_pet(now, str(zone_id), category, object_id, row)

        # Objects that were inside but are no longer: record their exit.
        for occ_key in list(self._inside_since):
            if occ_key in seen_inside:
                continue
            object_id, zone_id = occ_key
            del self._inside_since[occ_key]
            exit_category = self._category_of(object_id)
            if exit_category:
                self._last_exit[(zone_id, exit_category)] = (now, object_id)

    def _category_of(self, object_id: int) -> Optional[str]:
        category = self._object_categories.get(object_id)
        return category

    def _maybe_emit_pet(self, now: float, zone_id: str, category: str, object_id: int, row: dict) -> None:
        other = "pedestrian" if category == "vehicle" else "vehicle"
        last = self._last_exit.get((zone_id, other))
        if last is None:
            return
        exit_time, first_object_id = last
        pet = now - exit_time
        if pet <= 0 or pet > self.pet_window_seconds:
            return
        order = "pedestrian_first" if other == "pedestrian" else "vehicle_first"
        pet_key = (zone_id, first_object_id, object_id, order)
        if pet_key in self._pet_keys:
            return
        self._pet_keys.add(pet_key)
        speed = row.get("speed_kmh")
        self.pet_event_rows.append(
            {
                "camera_id": self.camera_id,
                "zone_id": zone_id,
                "first_object_id": first_object_id,
                "first_class": other,
                "second_object_id": object_id,
                "second_class": category,
                "first_exit_seconds": round(exit_time, 3),
                "second_entry_seconds": round(now, 3),
                "pet_seconds": round(pet, 3),
                "encroachment_order": order,
                "second_speed_kmh": _round_opt(float(speed) if speed is not None else None, 2),
                "critical": pet < self.pet_critical_seconds,
            }
        )

    # ------------------------------------------------------------------
    # Yielding opportunities
    # ------------------------------------------------------------------

    def _active_pedestrian_count(self, zone_id: str) -> int:
        return sum(1 for (_, ped_zone), _state in self._ped_states.items() if ped_zone == zone_id)

    def _update_yielding(self, now: float, vehicles: List[dict]) -> None:
        for row in vehicles:
            object_id = int(row["object_id"])
            speed = row.get("speed_kmh")
            for state in row.get("_zebra_zone_states", []):
                zone_id = state.get("zone_id")
                if not zone_id:
                    continue
                zone_id = str(zone_id)
                key = (object_id, zone_id)
                opportunity = self._yield_states.get(key)
                inside = bool(state.get("inside"))
                near = bool(state.get("near"))

                if opportunity is None:
                    if (
                        near
                        and not inside
                        and speed is not None
                        and float(speed) >= self.approach_min_speed_kmh
                        and self._active_pedestrian_count(zone_id) > 0
                    ):
                        self._yield_states[key] = {
                            "opened": now,
                            "approach_speed_kmh": float(speed),
                            "min_speed_kmh": float(speed),
                            "pedestrians_active": self._active_pedestrian_count(zone_id),
                            "last_seen": now,
                        }
                    continue

                opportunity["last_seen"] = now
                if speed is not None:
                    opportunity["min_speed_kmh"] = min(opportunity["min_speed_kmh"], float(speed))
                if inside:
                    self._resolve_yield(key, now, entered_zone=True)
                elif opportunity["min_speed_kmh"] <= self.yield_speed_kmh:
                    self._resolve_yield(key, now, entered_zone=False)
                elif self._active_pedestrian_count(zone_id) == 0:
                    # Pedestrians gone before the vehicle slowed or entered.
                    self._resolve_yield(key, now, entered_zone=False)

    def _resolve_yield(self, key: Tuple[int, str], now: float, entered_zone: bool, lost: bool = False) -> None:
        opportunity = self._yield_states.pop(key, None)
        if opportunity is None:
            return
        vehicle_id, zone_id = key
        if lost:
            outcome = "unresolved"
        elif entered_zone:
            outcome = "did_not_yield"
        elif opportunity["min_speed_kmh"] <= self.yield_speed_kmh:
            outcome = "yielded"
        else:
            outcome = "unresolved"
        self.yielding_event_rows.append(
            {
                "camera_id": self.camera_id,
                "zone_id": zone_id,
                "vehicle_object_id": vehicle_id,
                "vehicle_class": self._object_classes.get(vehicle_id),
                "opened_seconds": round(opportunity["opened"], 3),
                "resolved_seconds": round(now, 3),
                "approach_speed_kmh": round(opportunity["approach_speed_kmh"], 2),
                "min_approach_speed_kmh": round(opportunity["min_speed_kmh"], 2),
                "outcome": outcome,
                "pedestrians_active": opportunity["pedestrians_active"],
            }
        )

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _expire_stale(self, now: float) -> None:
        for key, ped in list(self._ped_states.items()):
            if now - ped.get("last_seen", now) > self.stale_after_seconds:
                self._close_ped_episode(key, now, outcome="lost")
        for key, opportunity in list(self._yield_states.items()):
            if now - opportunity.get("last_seen", now) > self.stale_after_seconds:
                self._resolve_yield(key, now, entered_zone=False, lost=True)

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def metric_summary(self) -> dict:
        waits = sorted(
            row["wait_seconds"] for row in self.pedestrian_episode_rows
            if row.get("wait_seconds") is not None
        )
        crossings = sorted(
            row["crossing_seconds"] for row in self.pedestrian_episode_rows
            if row.get("crossing_seconds") is not None
        )
        yielded = sum(1 for row in self.yielding_event_rows if row["outcome"] == "yielded")
        did_not = sum(1 for row in self.yielding_event_rows if row["outcome"] == "did_not_yield")
        unresolved = sum(1 for row in self.yielding_event_rows if row["outcome"] == "unresolved")
        decided = yielded + did_not
        pets = sorted(row["pet_seconds"] for row in self.pet_event_rows)
        return {
            "pedestrian_episodes": {
                "count": len(self.pedestrian_episode_rows),
                "completed": sum(1 for row in self.pedestrian_episode_rows if row["outcome"] == "crossed"),
                "avg_wait_seconds": _round_opt(sum(waits) / len(waits) if waits else None),
                "median_wait_seconds": _round_opt(median(waits) if waits else None),
                "p85_wait_seconds": _round_opt(_percentile(waits, 0.85)),
                "avg_crossing_seconds": _round_opt(sum(crossings) / len(crossings) if crossings else None),
                "median_crossing_seconds": _round_opt(median(crossings) if crossings else None),
            },
            "yielding": {
                "opportunities": len(self.yielding_event_rows),
                "yielded": yielded,
                "did_not_yield": did_not,
                "unresolved": unresolved,
                "yielding_rate": round(yielded / decided, 4) if decided else None,
            },
            "post_encroachment": {
                "events": len(self.pet_event_rows),
                "min_pet_seconds": _round_opt(min(pets) if pets else None),
                "median_pet_seconds": _round_opt(median(pets) if pets else None),
                "critical_events": sum(1 for row in self.pet_event_rows if row["critical"]),
                "critical_threshold_seconds": self.pet_critical_seconds,
            },
        }
