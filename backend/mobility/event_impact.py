"""Major-event demand model (all parameters are explicit, editable assumptions)."""
from __future__ import annotations

from typing import Dict, List, Tuple

from backend.gis import store
from backend.services.osm_service import haversine_km
from backend.simulation.network_model import NetworkModel

DEFAULTS = {"attendees": 40000, "car_share": 0.55, "occupancy": 2.4, "arrival_hours": 3.0, "parking_spaces": 6000,
            "metro_share": 0.25, "metro_capacity_pax_h": 12000, "background_growth_pct": 0}


def build_event(model: NetworkModel, place: str, **kw) -> Dict:
    a = {**DEFAULTS, **{k: v for k, v in kw.items() if v is not None}}
    node = model.resolve_place(place) or model.zones["KAFD"]
    cars_total = a["attendees"] * a["car_share"] / a["occupancy"]
    veh_per_h = cars_total / a["arrival_hours"]
    # origin shares follow the baseline gravity weights toward the venue node
    shares = {o: s for (o, d), s in model.T.items() if d == node}
    tot = sum(shares.values()) or 1.0
    lo, la = model.node_ll(node)
    # a venue is served by several nearby access nodes, not a single junction (otherwise one ramp absorbs everything)
    near = sorted((n for n in model.G.nodes if model.G.degree(n) >= 2), key=lambda n: haversine_km(model.node_ll(n), (lo, la)))
    access = [n for n in near[:8] if haversine_km(model.node_ll(n), (lo, la)) <= 2.0] or [node]
    extra: List[Tuple[str, str, float]] = [(o, a, veh_per_h * s / tot / len(access)) for o, s in shares.items() for a in access if o != a]
    stations = [r for r in store.list_("MetroStation") if haversine_km(r["geometry"]["coordinates"], (lo, la)) <= 1.2]
    metro_pax = a["attendees"] * a["metro_share"] / a["arrival_hours"]
    info = {
        "venue_node": node, "access_nodes": len(access), "venue": place, "assumptions": a, "event_vehicles_total": round(cars_total),
        "added_vehicles_per_hour": round(veh_per_h), "parking_spaces": a["parking_spaces"],
        "parking_deficit_vehicles": max(0, round(cars_total - a["parking_spaces"])),
        "metro_stations_within_1_2km": [s["name"] for s in stations],
        "metro_pax_per_hour": round(metro_pax),
        "metro_capacity_pax_per_hour": a["metro_capacity_pax_h"],
        "metro_utilisation": round(metro_pax / a["metro_capacity_pax_h"], 2) if stations else None,
        "note": "Metro capacity and parking supply are assumptions, not Riyadh Metro / venue operator data.",
    }
    return {"extra_od": extra, "info": info, "node": node}
