"""SEE / UNDERSTAND: multi-temporal change detection and feature extraction.

HONESTY NOTE: no real Sentinel-2 / Esri imagery is downloaded here. A reproducible *simulated* 4-band scene
(RED, NIR, SWIR, per epoch) is generated per area with injected land-cover changes, seasonal/illumination
differences and noise. The detection and extraction algorithms below are REAL (radiometric normalisation,
index differencing, adaptive threshold, morphology, connected components, convex-hull polygons) and are
meant to be pointed at real rasters through `load_scene()` when imagery is available. Every record produced is
labelled Data_Classification = SIMULATED-PROCESSING. Nothing is a confirmed construction event.
"""
from __future__ import annotations

import hashlib
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, utcnow
from backend.services import osm
from backend.services.synthetic import AREAS

N = 160            # pixels per side
CELL_M = 15.0      # metres per pixel
HALF_M = N * CELL_M / 2
EPOCH_A = "2021-06 (simulated)"
EPOCH_B = "2025-06 (simulated)"
EXTRACTION_SOURCE = "SIMULATED GeoAI (threshold + morphology on simulated imagery; no deep-learning model executed)"

# class signatures (red, nir, swir): 0 bare, 1 built, 2 vegetation, 3 asphalt/road
SIG = np.array([[0.30, 0.32, 0.35], [0.35, 0.30, 0.55], [0.08, 0.45, 0.20], [0.12, 0.13, 0.30]])


@dataclass
class Scene:
    area: str
    center: tuple[float, float]
    a: np.ndarray  # (3,N,N)
    b: np.ndarray
    truth_changes: list[dict]  # what was injected (simulator only; never shown as a detection)


def _seed_for(area: str, seed: int) -> int:
    return int(hashlib.sha256(f"{area}:{seed}".encode()).hexdigest()[:8], 16)


def px_to_lonlat(center, r: float, c: float):
    return geo.offset(center, (c - N / 2) * CELL_M, (N / 2 - r) * CELL_M)


def lonlat_to_px(center, p):
    dx = (p[0] - center[0]) * math.cos(math.radians(center[1])) * 111320.0
    dy = (p[1] - center[1]) * 110540.0
    return N / 2 - dy / CELL_M, dx / CELL_M + N / 2  # (row, col)


def _rasterise_osm(center, cls: np.ndarray) -> list[tuple[int, int]]:
    """Burn REAL OSM building footprints (class 1) and roads (class 3) into the class map. Returns building centroid pixels."""
    span = HALF_M * 1.45
    centres = []
    for b in osm.buildings_near(center, span):
        ring = [lonlat_to_px(center, q) for q in b["ring"]]
        rs, cs = [q[0] for q in ring], [q[1] for q in ring]
        r0, r1, c0, c1 = int(min(rs)), int(max(rs)) + 1, int(min(cs)), int(max(cs)) + 1
        rc, cc = lonlat_to_px(center, b["centroid"])
        if 0 <= int(rc) < N and 0 <= int(cc) < N:
            cls[int(rc), int(cc)] = 1
            centres.append((int(rc), int(cc)))
        for r in range(max(0, r0), min(N, r1)):
            for c in range(max(0, c0), min(N, c1)):
                if geo.point_in_ring((r + 0.5, c + 0.5), ring):
                    cls[r, c] = 1
    for r in osm.roads_near(center, span, osm.MAJOR + osm.LOCAL):
        pts = [lonlat_to_px(center, q) for q in r["coords"]]
        wide = r["highway"] in osm.MAJOR
        for (ra, ca), (rb, cb) in zip(pts, pts[1:]):
            steps = max(2, int(max(abs(rb - ra), abs(cb - ca)) * 2))
            for k in range(steps + 1):
                rr, cc = int(ra + (rb - ra) * k / steps), int(ca + (cb - ca) * k / steps)
                if 0 <= rr < N and 0 <= cc < N:
                    cls[rr, cc] = 3
                    if wide:
                        for dr, dc in ((1, 0), (0, 1)):
                            if rr + dr < N and cc + dc < N:
                                cls[rr + dr, cc + dc] = 3
    return centres


_cache: dict[tuple, Scene] = {}


def load_scene(area: str, seed: int = 20260101) -> Scene:
    key = (area, seed)
    if key in _cache:
        return _cache[key]
    rng = np.random.default_rng(_seed_for(area, seed))
    center = AREAS[area]["center"]
    n1 = ndi.gaussian_filter(rng.standard_normal((N, N)), 9)
    n1 = (n1 - n1.mean()) / n1.std()
    n2 = ndi.gaussian_filter(rng.standard_normal((N, N)), 6)
    n2 = (n2 - n2.mean()) / n2.std()
    cls = np.zeros((N, N), dtype=int)
    centres: list[tuple[int, int]] = []
    if osm.available():  # land cover rasterised from REAL OSM buildings/roads; open land = bare or vegetation
        cls[n2 > 0.9] = 2
        centres = _rasterise_osm(center, cls)
    else:
        cls[n1 > 0.2] = 1
        cls[(n1 <= 0.2) & (n2 > 0.7)] = 2
        for k in range(18, N, 36):  # fallback synthetic road grid
            cls[k:k + 2, :] = 3
            cls[:, k + 5:k + 7] = 3
    cls_a = cls.copy()
    cls_b = cls.copy()
    inj = []

    def rect(r0, c0, h, w):
        return slice(r0, r0 + h), slice(c0, c0 + w)

    def inject(kind, r0, c0, h, w, to):
        sl = rect(r0, c0, h, w)
        region = cls_b[sl]
        region[region != 3] = to
        inj.append({"kind": kind, "r": r0, "c": c0, "h": h, "w": w})

    used = np.zeros((N, N), dtype=bool)

    def free(h, w):  # a spot centred on a real building if OSM is available, mostly clear of roads and of earlier injections
        for attempt in range(4000):
            if centres and attempt < 3000:
                rc, cc = centres[int(rng.integers(0, len(centres)))]
                r0, c0 = rc - h // 2, cc - w // 2
                if r0 < 5 or c0 < 5 or r0 + h > N - 5 or c0 + w > N - 5:
                    continue
            else:
                r0, c0 = int(rng.integers(5, N - h - 5)), int(rng.integers(5, N - w - 5))
            if used[max(0, r0 - 6):r0 + h + 6, max(0, c0 - 6):c0 + w + 6].any():
                continue
            if (cls[r0:r0 + h, c0:c0 + w] == 3).mean() < (0.2 if centres else 0.001):
                used[r0:r0 + h, c0:c0 + w] = True
                return r0, c0
        raise RuntimeError("could not place simulated change")

    def set_nonroad(arr, r0, c0, h, w, val):
        reg = arr[r0:r0 + h, c0:c0 + w]
        reg[reg != 3] = val

    for kind, to, h, w in (("new_construction", 1, 10, 12), ("new_construction", 1, 8, 9), ("new_construction", 1, 12, 8),
                           ("clearing", 0, 9, 10), ("seasonal_vegetation", 2, 11, 11)):
        r0, c0 = free(h, w)
        if kind == "seasonal_vegetation":  # a vegetated field that is just drier in epoch B
            set_nonroad(cls_a, r0, c0, h, w, 2)
            set_nonroad(cls_b, r0, c0, h, w, 2)
            inj.append({"kind": kind, "r": r0, "c": c0, "h": h, "w": w})
        elif kind == "clearing":
            set_nonroad(cls_a, r0, c0, h, w, 1)
            inject(kind, r0, c0, h, w, to)
        else:  # simulated 'before' state = open land; 'after' = built
            set_nonroad(cls_a, r0, c0, h, w, int(rng.choice([0, 2])))
            inject(kind, r0, c0, h, w, to)

    a = SIG[cls_a].transpose(2, 0, 1).copy()
    b = SIG[cls_b].transpose(2, 0, 1).copy()
    # seasonal / illumination differences (the distractors a naive detector would flag)
    for s in inj:
        if s["kind"] == "seasonal_vegetation":
            sl = rect(s["r"], s["c"], s["h"], s["w"])
            b[1][sl] *= 0.62   # drier vegetation: NIR drops
            b[0][sl] *= 1.5
    veg_b = cls_b == 2
    b[1][veg_b] *= 0.93
    b = b * rng.uniform(1.04, 1.08) + rng.uniform(0.012, 0.025)      # illumination gain/offset
    a = a + rng.normal(0, 0.012, a.shape)
    b = b + rng.normal(0, 0.012, b.shape)
    b = np.roll(b, 0, axis=2)
    sc = Scene(area, center, np.clip(a, 0.01, 1), np.clip(b, 0.01, 1), inj)
    _cache[key] = sc
    return sc


def _ndvi(x):
    return (x[1] - x[0]) / (x[1] + x[0] + 1e-9)


def _ndbi(x):
    return (x[2] - x[1]) / (x[2] + x[1] + 1e-9)


def normalise(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-band linear radiometric normalisation of B to A using pseudo-invariant pixels (central 60% of |diff|)."""
    out = np.empty_like(b)
    for i in range(b.shape[0]):
        d = np.abs(a[i] - b[i])
        lo, hi = np.percentile(d, [10, 70])
        m = (d >= lo) & (d <= hi)
        sa, sb = a[i][m].std(), b[i][m].std()
        gain = sa / sb if sb > 1e-9 else 1.0
        off = a[i][m].mean() - gain * b[i][m].mean()
        out[i] = b[i] * gain + off
    return out


def detect_changes(store: Store, area: str, seed: int = 20260101, k_sigma: float = 4.0, min_pixels: int = 8,
                   significant_area_sqm: float = 2500.0, min_confidence: float = 0.6) -> dict:
    if area not in AREAS:
        raise ValueError(f"unknown area {area}; choose one of {list(AREAS)}")
    sc = load_scene(area, seed)
    bn = normalise(sc.a, sc.b)
    d_ndvi = _ndvi(bn) - _ndvi(sc.a)
    d_ndbi = _ndbi(bn) - _ndbi(sc.a)
    mag = np.sqrt(d_ndvi ** 2 + d_ndbi ** 2)
    med = np.median(mag)
    mad = np.median(np.abs(mag - med)) * 1.4826
    thr = float(med + k_sigma * mad)
    mask = ndi.binary_opening(mag > thr, structure=np.ones((3, 3)))
    lab, n = ndi.label(mask)
    code = AREAS[area]["code"]
    # idempotent per area/epoch pair: replace previous candidates that are not yet linked to incidents
    for f in store.query(S.CHANGES, Area_Name=area, Previous_Epoch=EPOCH_A, Current_Epoch=EPOCH_B):
        store.delete(S.CHANGES, f["id"])
    results = []
    idx = 0
    for comp in range(1, n + 1):
        ys, xs = np.where(lab == comp)
        if len(ys) < min_pixels:
            continue
        idx += 1
        m_ndbi, m_ndvi, m_mag = float(d_ndbi[ys, xs].mean()), float(d_ndvi[ys, xs].mean()), float(mag[ys, xs].mean())
        area_sqm = float(len(ys) * CELL_M ** 2)
        m_ndbi_b = float(_ndbi(bn)[ys, xs].mean())
        if m_ndbi > 0.12 and m_ndbi_b > 0.05:
            ctype, built_signal = "New construction (candidate)", True
        elif m_ndbi > 0.12:
            ctype, built_signal = "Vegetation loss (possible seasonal - unconfirmed)", False
        elif m_ndbi < -0.12:
            ctype, built_signal = "Clearing / demolition (candidate)", False
        elif m_ndvi < -0.15:
            ctype, built_signal = "Vegetation loss (possible seasonal - unconfirmed)", False
        else:
            ctype, built_signal = "Spectral change (unclassified)", False
        conf = float(np.clip(0.45 + 0.4 * math.tanh((m_mag - thr) / 0.25) + 0.15 * min(1.0, area_sqm / 6000), 0.05, 0.97))
        significant = built_signal and area_sqm >= significant_area_sqm and conf >= min_confidence
        pts = np.array([[c + dc, r + dr] for r, c in zip(ys, xs) for dr in (0, 1) for dc in (0, 1)], dtype=float)
        hull = pts[ConvexHull(pts).vertices] if len(pts) >= 3 else pts
        ring = [px_to_lonlat(sc.center, r, c) for c, r in hull]
        notes = ("Index-differencing candidate on SIMULATED imagery. Not a confirmed construction event; requires field/analyst verification."
                 + (" Vegetation-only change may be seasonal or irrigation-related." if ctype.startswith("Vegetation") else ""))
        cid = f"CHG-{code}-{idx:03d}"
        store.upsert(S.CHANGES, {"Change_ID": cid, "Change_Type": ctype, "Previous_Epoch": EPOCH_A, "Current_Epoch": EPOCH_B, "Area_Sqm": round(area_sqm, 0),
                                 "Confidence": round(conf, 2), "Detection_Date": utcnow(), "Status": "Candidate", "Area_Name": area,
                                 "Significant": "Yes" if significant else "No", "Mean_Magnitude": round(m_mag, 3), "Notes": notes,
                                 "Data_Classification": S.SIMULATED}, geo.polygon(ring))
        results.append({"change_id": cid, "type": ctype, "area_sqm": round(area_sqm), "confidence": round(conf, 2), "significant": significant,
                        "mean_ndbi_change": round(m_ndbi, 3), "mean_ndvi_change": round(m_ndvi, 3)})
    # score the detector against the injected truth (simulation-only quality check)
    truth_hits = 0
    for t in sc.truth_changes:
        if t["kind"] == "seasonal_vegetation":
            continue
        sub = lab[t["r"]:t["r"] + t["h"], t["c"]:t["c"] + t["w"]]
        truth_hits += int((sub > 0).mean() > 0.4)
    injected_real = sum(1 for t in sc.truth_changes if t["kind"] != "seasonal_vegetation")
    return {"area": area, "previous_epoch": EPOCH_A, "current_epoch": EPOCH_B, "simulated_imagery": True, "threshold": round(thr, 4),
            "method": f"radiometric normalisation -> NDVI/NDBI differencing -> adaptive threshold (median+{k_sigma}*MAD) -> opening -> connected components",
            "changes": results, "significant_count": sum(1 for r in results if r["significant"]),
            "simulation_check": {"injected_real_changes": injected_real, "recovered": truth_hits,
                                 "note": "Simulator-only check against injected changes; not available on real imagery."}}


# ---------------------------------------------------------------------------------------------------------
def extract_features(store: Store, change_id: str, seed: int = 20260101) -> dict:
    """UNDERSTAND: extract building footprints and road segments around a change polygon from the CURRENT epoch."""
    ch = store.get(S.CHANGES, change_id)
    if not ch:
        raise ValueError(f"change {change_id} not found")
    area = ch["attrs"]["Area_Name"]
    sc = load_scene(area, seed)
    bn = normalise(sc.a, sc.b)
    ring = [tuple(p) for p in ch["geom"]["coordinates"][0]]
    cx, cy = geo.centroid(ch["geom"])
    # window: change bbox expanded by 25 px
    def to_px(p):
        dx = (p[0] - sc.center[0]) * math.cos(math.radians(sc.center[1])) * 111320
        dy = (p[1] - sc.center[1]) * 110540
        return (N / 2 - dy / CELL_M, dx / CELL_M + N / 2)
    prs = np.array([to_px(p) for p in ring])
    r0, r1 = int(max(0, prs[:, 0].min() - 25)), int(min(N, prs[:, 0].max() + 25))
    c0, c1 = int(max(0, prs[:, 1].min() - 25)), int(min(N, prs[:, 1].max() + 25))
    win = bn[:, r0:r1, c0:c1]
    hh, ww = win.shape[1:]
    # pixels inside the change polygon, dilated by 2 px: buildings are extracted only where the change occurred
    inside = np.zeros((hh, ww), dtype=bool)
    pr = [(p[0], p[1]) for p in prs]
    for r in range(hh):
        for c in range(ww):
            inside[r, c] = geo.point_in_ring((r0 + r + 0.5, c0 + c + 0.5), pr)
    inside = ndi.binary_dilation(inside, iterations=2)
    built = ndi.binary_opening(_ndbi(win) > 0.18, structure=np.ones((2, 2))) & inside
    asphalt = (win[0] < 0.17) & (win[1] < 0.19) & (win[2] < 0.36)
    for old in store.query(S.FEATURES, Related_Change_ID=change_id):
        store.delete(S.FEATURES, old["id"])
    out = {"buildings": [], "roads": []}
    lab, n = ndi.label(built)
    for k in range(1, n + 1):
        ys, xs = np.where(lab == k)
        if len(ys) < 6:
            continue
        ra, rb, ca, cb = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        ringb = [px_to_lonlat(sc.center, r0 + r, c0 + c) for r, c in ((ra, ca), (ra, cb), (rb, cb), (rb, ca))]
        fid = store.next_id("FT")
        conf = round(float(min(0.9, 0.55 + len(ys) / (((rb - ra) * (cb - ca)) or 1) * 0.35)), 2)
        store.upsert(S.FEATURES, {"Feature_ID": fid, "Feature_Type": "Building footprint", "Extraction_Source": EXTRACTION_SOURCE, "Confidence": conf,
                                  "Area_Sqm": round(len(ys) * CELL_M ** 2, 0), "Detection_Date": utcnow(), "Related_Change_ID": change_id, "Length_M": None,
                                  "Data_Classification": S.SIMULATED}, geo.polygon(ringb))
        out["buildings"].append({"feature_id": fid, "area_sqm": round(len(ys) * CELL_M ** 2), "confidence": conf})
    claimed = np.zeros_like(asphalt)
    ident = np.eye(7, dtype=bool)
    for struct_el in (np.ones((1, 7), bool), np.ones((7, 1), bool), ident, ident[:, ::-1]):
        lab, n = ndi.label(ndi.binary_opening(asphalt, structure=struct_el))
        for k in range(1, n + 1):
            ys, xs = np.where(lab == k)
            if len(ys) < 10 or claimed[ys, xs].mean() > 0.5:
                continue
            claimed[ys, xs] = True
            pts = np.c_[xs + 0.5, ys + 0.5]
            ctr = pts.mean(axis=0)
            w_, v_ = np.linalg.eigh(np.cov((pts - ctr).T))
            ax = v_[:, int(np.argmax(w_))]
            proj = (pts - ctr) @ ax
            pa_px, pb_px = ctr + ax * proj.min(), ctr + ax * proj.max()
            pa = px_to_lonlat(sc.center, r0 + pa_px[1], c0 + pa_px[0])
            pb = px_to_lonlat(sc.center, r0 + pb_px[1], c0 + pb_px[0])
            L = geo.haversine_m(pa, pb)
            if L < 3 * CELL_M:
                continue
            nx, ny = -ax[1], -ax[0]  # unit normal in (east, north) metres
            hw = CELL_M / 2
            ringr = [geo.offset(pa, nx * hw, ny * hw), geo.offset(pb, nx * hw, ny * hw), geo.offset(pb, -nx * hw, -ny * hw), geo.offset(pa, -nx * hw, -ny * hw)]
            fid = store.next_id("FT")
            store.upsert(S.FEATURES, {"Feature_ID": fid, "Feature_Type": "Road segment", "Extraction_Source": EXTRACTION_SOURCE, "Confidence": 0.7,
                                      "Area_Sqm": None, "Detection_Date": utcnow(), "Related_Change_ID": change_id, "Length_M": round(L, 0),
                                      "Data_Classification": S.SIMULATED}, geo.polygon(ringr))
            out["roads"].append({"feature_id": fid, "length_m": round(L)})
    out.update({"change_id": change_id, "area": area, "simulated": True, "source": EXTRACTION_SOURCE,
                "window_px": [r0, r1, c0, c1]})
    return out


# ---------------------------------------------------------------------------------------------------------
def render_png(area: str, epoch: str, seed: int = 20260101) -> bytes:
    """False-colour composite (R=SWIR, G=NIR, B=RED) as PNG, using only numpy+zlib."""
    sc = load_scene(area, seed)
    arr = sc.a if epoch == "A" else normalise(sc.a, sc.b) if epoch == "Bn" else sc.b
    rgb = np.stack([arr[2], arr[1], arr[0]], axis=-1)
    rgb = (np.clip(rgb / 0.65, 0, 1) * 255).astype(np.uint8)
    rgb = np.kron(rgb, np.ones((3, 3, 1), dtype=np.uint8))
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def scene_bounds(area: str) -> dict:
    c = AREAS[area]["center"]
    sw, ne = geo.offset(c, -HALF_M, -HALF_M), geo.offset(c, HALF_M, HALF_M)
    return {"xmin": sw[0], "ymin": sw[1], "xmax": ne[0], "ymax": ne[1]}
