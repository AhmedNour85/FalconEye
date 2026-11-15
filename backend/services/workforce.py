"""Field-team recommendation: skills, proximity and workload."""
from __future__ import annotations

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store

SKILL_FOR = {"water": "water", "lighting": "electrical", "change": "survey", "distortion": "survey", "land_use": "survey"}
TEAM_FOR = {"water": "Water Rapid Response", "lighting": "Electrical Maintenance", "change": "Survey & Inspection", "distortion": "Survey & Inspection", "land_use": "Survey & Inspection"}


def rank_workers(store: Store, location: tuple[float, float], category: str, task: str = "") -> list[dict]:
    skill = SKILL_FOR.get(category, "inspection")
    ranked = []
    for w in store.all(S.WORKERS):
        a = w["attrs"]
        skills = a["Skills"].split(",")
        d = geo.haversine_m(location, geo.centroid(w["geom"]))
        skill_score = 1.0 if skill in skills else (0.5 if "inspection" in skills and task == "inspect" else 0.0)
        prox = max(0.0, 1 - d / 12000)
        load = max(0.0, 1 - a["Open_Tasks"] / 4)
        score = round(100 * (0.5 * skill_score + 0.3 * prox + 0.2 * load), 1)
        ranked.append({"worker_id": a["Worker_ID"], "name": a["Name"], "team": a["Team"], "skills": skills, "distance_m": round(d),
                       "open_tasks": a["Open_Tasks"], "status": a["Status"], "score": score,
                       "rationale": f"skill match={'yes' if skill_score == 1 else 'partial' if skill_score else 'no'}, {d / 1000:.1f} km away, {a['Open_Tasks']} open task(s)"})
    ranked.sort(key=lambda r: -r["score"])
    return ranked
