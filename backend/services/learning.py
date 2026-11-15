"""LEARN stage: feedback records, evaluation metrics and configurable risk calibration.

This does NOT retrain any ML model. Verified outcomes update (a) evaluation metrics and (b) a per-category
risk calibration multiplier plus the streetlight detection threshold stored in Riyadh_Learning_Config.
Model retraining is a separate, controlled offline process (see docs/architecture.md).
"""
from __future__ import annotations

from backend.gis import schema as S
from backend.gis.store import Store, utcnow

PRIOR_PRECISION = 0.75
CATS = ("water", "lighting", "change", "distortion", "land_use")


def get_cfg(store: Store, key: str, default: float = 1.0) -> float:
    f = store.get(S.CONFIG, key)
    try:
        return float(f["attrs"]["Value"]) if f else default
    except (TypeError, ValueError):
        return default


def calibration(store: Store, category: str) -> float:
    return get_cfg(store, f"calibration.{category}", 1.0)


def verified_detections(store: Store, category: str | None = None) -> list[dict]:
    out = []
    for f in store.all(S.DETECTIONS):
        a = f["attrs"]
        if a["Status"] in ("Verified-True", "Verified-False") and (category is None or a["Category"] == category):
            out.append(a)
    return out


def recalibrate(store: Store) -> dict:
    """Update calibration multipliers from verified outcomes (Laplace-smoothed precision vs. prior)."""
    changes = {}
    for cat in CATS:
        v = verified_detections(store, cat)
        tp = sum(1 for a in v if a["Status"] == "Verified-True")
        n = len(v)
        precision = (tp + 1) / (n + 2)
        new = round(max(0.70, min(1.15, precision / PRIOR_PRECISION)), 3)
        old = calibration(store, f"{cat}".replace("calibration.", ""))
        store.upsert(S.CONFIG, {"Config_ID": f"calibration.{cat}", "Value": str(new), "Updated": utcnow()})
        changes[cat] = {"verified": n, "true_positives": tp, "smoothed_precision": round(precision, 3), "old_calibration": old, "new_calibration": new}
    # streetlight threshold: raise when many lighting predictions are false positives
    v = verified_detections(store, "lighting")
    if len(v) >= 4:
        fp_rate = sum(1 for a in v if a["Status"] == "Verified-False") / len(v)
        thr = round(max(0.50, min(0.75, 0.50 + 0.5 * fp_rate)), 3)
        store.upsert(S.CONFIG, {"Config_ID": "streetlight.detect_threshold", "Value": str(thr), "Updated": utcnow()})
        changes["streetlight_threshold"] = thr
    return changes


def apply_calibration(store: Store, category: str, base_score: float) -> float:
    return round(max(0.0, min(100.0, base_score * calibration(store, category))), 1)


def evaluation(store: Store) -> dict:
    """Prediction vs. verified condition. FN only where simulator ground truth exists (labelled as such)."""
    dets = [f["attrs"] for f in store.all(S.DETECTIONS)]
    truth = {f["attrs"]["Truth_ID"]: f["attrs"]["Is_True"] for f in store.all(S.TRUTH)}
    out = {"categories": {}, "notes": "False negatives are computed from simulator ground truth (not available in production)."}
    tot_tp = tot_fp = 0
    for cat in CATS:
        cd = [d for d in dets if d["Category"] == cat]
        tp = sum(1 for d in cd if d["Status"] == "Verified-True")
        fp = sum(1 for d in cd if d["Status"] == "Verified-False")
        pending = sum(1 for d in cd if d["Status"] not in ("Verified-True", "Verified-False"))
        fn = None
        if cat == "lighting":
            detected = {d["Related_Asset_ID"] for d in cd}
            fn = sum(1 for k, v in truth.items() if k.startswith("AST-L-") and v == "Yes" and k not in detected)
        elif cat == "water":
            detected = {d["Pipeline_ID"] for d in cd}
            fn = sum(1 for k, v in truth.items() if k.startswith("PIPE-") and v == "Yes" and k not in detected)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if fn is not None and tp + fn else None
        out["categories"][cat] = {"detections": len(cd), "verified_true": tp, "verified_false": fp, "awaiting_verification": pending,
                                  "false_negatives_known": fn, "precision": None if prec is None else round(prec, 3),
                                  "recall": None if rec is None else round(rec, 3), "calibration": calibration(store, cat)}
        tot_tp += tp
        tot_fp += fp
    out["overall_precision"] = round(tot_tp / (tot_tp + tot_fp), 3) if tot_tp + tot_fp else None
    out["total_verified"] = tot_tp + tot_fp
    out["total_detections"] = len(dets)
    out["verification_rate"] = round((tot_tp + tot_fp) / len(dets), 3) if dets else None
    out["streetlight_threshold"] = get_cfg(store, "streetlight.detect_threshold", 0.55)
    series = sorted(({"date": d["Detection_Date"][:10], "category": d["Category"], "outcome": d["Status"]} for d in dets if d["Status"] in ("Verified-True", "Verified-False")),
                    key=lambda x: x["date"])
    out["outcomes"] = series
    return out
