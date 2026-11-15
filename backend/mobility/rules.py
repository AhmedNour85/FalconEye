"""The small tables the mobility crew decides by. Numbers here are choices, not measurements: change them here only."""
from __future__ import annotations

# Road impact of a repair next to a modelled road (the cross-domain link). One row per repair category.
#   radius_m      a road section closer than this to the incident is affected
#   lanes         lanes the repair closes; a road with this many lanes or fewer is closed completely
#   day / night   the two working windows compared, as (start hour, end hour)
#   night_saving  night is recommended when it costs at least this share fewer trip-hours than day
ROAD_IMPACT = {"water": {"radius_m": 60, "lanes": 2, "day": (8, 16), "night": (22, 6), "night_saving": 0.10}}

SMALL_IMPACT_TRIP_HOURS = 50      # under this in both windows the alert says the impact is small
ABNORMAL_VC = 0.85                # volume / capacity from which a road section counts as "heavy" (network_model.flow_class)
INCIDENT_WINDOW_HOURS = 2         # how long a blocked-lane report is assumed to last when its impact is simulated

CAP = 95


def report_risk(lanes: int, lanes_blocked: int, road_class: str, vc_after: float | None) -> float:
    """Risk score of a blocked-lane report. `vc_after` is the modelled load with the lanes blocked, or None when the model is not ready."""
    share = min(1.0, max(0, lanes_blocked) / max(1, lanes))
    score = 40 + 30 * share + (15 if road_class == "motorway" else 0) + (20 if vc_after is not None and vc_after >= ABNORMAL_VC else 0)
    return float(min(CAP, round(score, 1)))


def closure_risk(road_class: str, full: bool, hours: float) -> float:
    return float(min(CAP, round(50 + (15 if road_class == "motorway" else 0) + (10 if full else 0) + min(15.0, max(0.0, hours)), 1)))


def event_risk(attendance: int) -> float:
    return float(min(CAP, round(45 + min(40.0, max(0, attendance) / 2000), 1)))
