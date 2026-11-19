"""Graph-based transportation network model (NetworkX) with a documented static traffic assignment.

WHAT THIS IS: macroscopic network analysis - gravity-model OD demand, all-or-nothing shortest paths blended by the
Method of Successive Averages (MSA) with BPR volume-delay functions (t = t0 * (1 + 0.15 (v/c)^4)).
WHAT THIS IS NOT: a validated microsimulation (see sumo_adapter.py) nor a calibrated model of real Riyadh demand.
The baseline network is never mutated: scenarios operate on clones.
"""
from __future__ import annotations

import copy
import math
import threading
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import networkx as nx

from backend.mobility import riyadh_network as RN
from backend.mobility.sources import haversine_km

BPR_ALPHA, BPR_BETA = 0.15, 4.0
# Demand-weighted mean OD travel time at the daily peak / free-flow time. TomTom's Traffic Index reports ~44% average extra travel time for Riyadh
# over the year (rush hours are worse), so 1.7x at the peak is a plausible ASSUMPTION, not a calibrated measurement.
TARGET_PEAK_DELAY_RATIO = 1.7
NORMAL_VC, SEVERE_VC = 0.70, 0.95

ASSUMPTIONS = [
    "Static user-equilibrium-like assignment (MSA, 15 iterations) on a macroscopic graph; no signals, queues or spillback.",
    "OD demand is a synthetic gravity model weighted around named activity centres, calibrated (bisection) so the demand-weighted mean peak OD travel time is ~1.5x free-flow.",
    "Travel time follows the BPR function (alpha=0.15, beta=4) over free-flow time at the posted speed limit.",
    "Per-direction capacity = lanes x 1800 (motorway) / 1500 (arterial) / 1200 (collector) veh/h.",
    "Time-of-day demand follows a synthetic Riyadh weekday profile (peaks ~08:00 and ~17:00).",
    "Results are estimates for comparison between scenarios, not forecasts or validated traffic simulation outputs.",
]


FLOW_COLORS = {"free": "#2faa4a", "slow": "#f5a21d", "heavy": "#e2362b", "stopped": "#8b1117"}


def flow_class(vc: float) -> str:
    """Google-Maps-style 4 tiers for DISPLAY (free / slow / heavy / stop-and-go) from modelled v/c. Not Google data."""
    return "free" if vc < 0.6 else "slow" if vc < 0.85 else "heavy" if vc < 1.1 else "stopped"


def level(vc: float) -> str:
    return "normal" if vc < NORMAL_VC else ("moderate" if vc < SEVERE_VC else "severe")


class NetworkModel:
    def __init__(self, segments: List[dict], nodes: Dict[str, dict], intersections: Dict[str, tuple]):
        self.G = nx.DiGraph()
        self.segments = {s["id"]: s for s in segments}
        self.closed: set = set()
        self.added: List[dict] = []
        self.narrowed: Dict[str, float] = {}   # segment id -> capacity left after a lane closure (Riyadh City View)
        self.nodes = nodes
        for nid, (lon, lat) in intersections.items():
            self.G.add_node(nid, lon=lon, lat=lat)
        for s in segments:
            coords = s["geometry"]["coordinates"]
            t0 = s["length_km"] / max(s["speed_limit"], 10) * 60.0  # minutes
            dirs = [(s["from_node"], s["to_node"], coords), (s["to_node"], s["from_node"], coords[::-1])]
            if (s.get("attributes") or {}).get("oneway"):
                dirs = dirs[:1]  # OSM one-way carriageway
            for u, v, c in dirs:
                self.G.add_edge(u, v, seg=s["id"], length=s["length_km"], t0=t0, t=t0, cap=float(s["capacity"]),
                                cls=s["road_class"], corridor=s["corridor"], coords=c, flow=0.0)
        self.zones = {k: self._nearest(lon, lat) for k, (_, lon, lat) in RN.LOCATIONS.items()}
        self.zone_nodes = self._choose_zones()
        self.T = self._gravity()
        self.trip_scale = 20000.0
        self._cache: Dict[float, dict] = {}
        self._lock = threading.RLock()

    # ---------- construction helpers ----------
    def _nearest(self, lon: float, lat: float) -> str:
        return min(self.G.nodes, key=lambda n: (self.G.nodes[n]["lon"] - lon) ** 2 + (self.G.nodes[n]["lat"] - lat) ** 2)

    def _choose_zones(self, n_max: int = 40) -> List[str]:
        """Small networks: every node is a demand zone. Large (OSM) networks: named places + farthest-point sample, so the
        OD matrix stays tractable (n_max^2 pairs) while covering the whole extent."""
        nodes = list(self.G.nodes)
        if len(nodes) <= 400:
            return nodes
        chosen = list(dict.fromkeys(self.zones.values()))
        pts = {n: (self.G.nodes[n]["lon"], self.G.nodes[n]["lat"]) for n in nodes}
        cand = [n for n in nodes if self.G.degree(n) >= 3] or nodes
        dmin = {n: min(haversine_km(pts[n], pts[c]) for c in chosen) for n in cand}
        while len(chosen) < n_max and dmin:
            far = max(dmin, key=dmin.get)
            if dmin[far] < 2.0:
                break
            chosen.append(far)
            dmin = {n: min(d, haversine_km(pts[n], pts[far])) for n, d in dmin.items() if n != far}
        return chosen

    def _gravity(self) -> Dict[Tuple[str, str], float]:
        w_loc = {"KAFD": 6, "Olaya": 6, "KKIA": 3, "RiyadhFront": 4, "KSU": 4, "Malaz": 4, "Nakheel": 3}
        weight = {}
        for n in self.zone_nodes:
            d = self.G.nodes[n]
            w = 1.0
            for k, (_, lo, la) in RN.LOCATIONS.items():
                dist = haversine_km((d["lon"], d["lat"]), (lo, la))
                w += w_loc.get(k, 2) * math.exp(-(dist / 3.0) ** 2)
            weight[n] = w
        T, tot = {}, 0.0
        for o in self.zone_nodes:
            for d in self.zone_nodes:
                if o == d:
                    continue
                dist = haversine_km((self.G.nodes[o]["lon"], self.G.nodes[o]["lat"]),
                                    (self.G.nodes[d]["lon"], self.G.nodes[d]["lat"]))
                T[(o, d)] = weight[o] * weight[d] * math.exp(-0.10 * dist)
                tot += T[(o, d)]
        return {k: v / tot for k, v in T.items()}  # normalised share; scaled by trip_scale (veh/h at peak)

    def clone(self) -> "NetworkModel":
        m = copy.copy(self)
        m.G = self.G.copy()
        m.closed = set(self.closed)
        m.added = list(self.added)
        m.narrowed = dict(self.narrowed)
        m._cache = {}
        m._lock = threading.RLock()
        m._crit_cache = None
        m._conn = None
        return m

    # ---------- scenario mutations (clone only) ----------
    def close_segments(self, seg_ids: Iterable[str]):
        for sid in seg_ids:
            self.closed.add(sid)
            for u, v, d in list(self.G.edges(data=True)):
                if d["seg"] == sid:
                    self.G.remove_edge(u, v)

    def reduce_capacity(self, seg_ids: Iterable[str], lanes_closed: int) -> Dict[str, float]:
        """Lane closure (new in Riyadh City View): each segment keeps capacity x (lanes - lanes_closed) / lanes, in every
        direction it carries. A segment with no lane left is closed. Returns segment id -> capacity left per direction."""
        if lanes_closed <= 0:
            raise ValueError("lanes_closed must be 1 or more")
        left: Dict[str, float] = {}
        shut = []
        for sid in seg_ids:
            seg = self.segments[sid]
            lanes = max(1, int(seg["lanes"]))
            if lanes_closed >= lanes:
                shut.append(sid); left[sid] = 0.0
                continue
            f = (lanes - lanes_closed) / lanes
            for _u, _v, e in self.G.edges(data=True):
                if e["seg"] == sid:
                    e["cap"] *= f
            left[sid] = self.narrowed[sid] = float(seg["capacity"]) * f
        if shut:
            self.close_segments(shut)
        return left

    def add_link(self, a: str, b: str, lanes: int = 3, speed: float = 80, name: str = "Proposed link"):
        la, lb = self.G.nodes[a], self.G.nodes[b]
        coords = [[la["lon"], la["lat"]], [lb["lon"], lb["lat"]]]
        length = haversine_km(coords[0], coords[1]) * 1.15  # sinuosity allowance
        sid = f"new-{len(self.added) + 1:02d}"
        t0 = length / speed * 60
        for u, v, c in ((a, b, coords), (b, a, coords[::-1])):
            self.G.add_edge(u, v, seg=sid, length=length, t0=t0, t=t0, cap=float(lanes * 1500), cls="arterial",
                            corridor=name, coords=c, flow=0.0, new=True)
        self.segments[sid] = dict(id=sid, name=name, corridor=name, road_class="arterial", lanes=lanes, length_km=length,
                                  speed_limit=speed, capacity=lanes * 1500, from_node=a, to_node=b,
                                  geometry={"type": "LineString", "coordinates": coords})
        self.added.append({"id": sid, "from": a, "to": b, "lanes": lanes, "speed": speed, "length_km": round(length, 2)})
        return sid

    # ---------- assignment ----------
    def assign(self, demand_scale: float = 1.0, od_mult: Optional[Callable[[str, str], float]] = None,
               extra_od: Optional[List[Tuple[str, str, float]]] = None, iterations: int = 15, use_cache: bool = True) -> dict:
        with self._lock:
            return self._assign(demand_scale, od_mult, extra_od, iterations, use_cache)

    def _assign(self, demand_scale, od_mult, extra_od, iterations, use_cache) -> dict:
        """Static assignment: MSA over BPR times; shortest paths via scipy.sparse.csgraph (C) and vectorised path loading,
        so a ~4,700-edge OSM network assigns in about a second."""
        import numpy as np
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        key = round(demand_scale, 4)
        plain = od_mult is None and not extra_od and not self.closed and not self.added and not self.narrowed
        if use_cache and plain and key in self._cache:
            return self._cache[key]
        G = self.G
        nodes = list(G.nodes)
        n = len(nodes)
        idx = {v: i for i, v in enumerate(nodes)}
        edges = list(G.edges(data=True))
        m = len(edges)
        eu = np.fromiter((idx[u] for u, _, _ in edges), dtype=np.int64, count=m)
        ev = np.fromiter((idx[v] for _, v, _ in edges), dtype=np.int64, count=m)
        t0 = np.fromiter((e["t0"] for _, _, e in edges), dtype=float, count=m)
        cap = np.fromiter((e["cap"] for _, _, e in edges), dtype=float, count=m)
        keys = eu * n + ev
        order = np.argsort(keys)
        skeys = keys[order]
        # demand
        pairs, dem = [], []
        for (o, d), share in self.T.items():
            if o in idx and d in idx:
                f = share * self.trip_scale * demand_scale
                if od_mult:
                    f *= od_mult(o, d)
                pairs.append((o, d)); dem.append(f)
        pos = {p: i for i, p in enumerate(pairs)}
        for o, d, tr in extra_od or []:
            if o in idx and d in idx:
                if (o, d) in pos:
                    dem[pos[(o, d)]] += tr
                else:
                    pos[(o, d)] = len(pairs); pairs.append((o, d)); dem.append(tr)
        dem = np.asarray(dem, dtype=float)
        origins = sorted({o for o, _ in pairs})
        orow = {o: i for i, o in enumerate(origins)}
        oi = np.asarray([orow[o] for o, _ in pairs]); di = np.asarray([idx[d] for _, d in pairs]); osrc = np.asarray([idx[o] for o, _ in pairs])
        src_idx = [idx[o] for o in origins]
        flow = np.zeros(m)
        t = t0.copy()

        def sp(tt):
            g = csr_matrix((tt, (eu, ev)), shape=(n, n))
            return dijkstra(g, directed=True, indices=src_idx, return_predecessors=True)

        unserved = 0.0
        for k in range(1, iterations + 1):
            dist, pred = sp(t)
            ok = np.isfinite(dist[oi, di])
            unserved = float(dem[~ok].sum())
            aon = np.zeros(m)
            cur = di[ok].copy(); rows = oi[ok]; src = osrc[ok]; w = dem[ok]
            active = cur != src
            while active.any():
                c = cur[active]; p = pred[rows[active], c]
                ei = order[np.searchsorted(skeys, p * n + c)]
                np.add.at(aon, ei, w[active])
                cur[active] = p
                active = cur != src
            lam = 1.0 / k
            flow = flow * (1 - lam) + aon * lam
            t = t0 * (1 + BPR_ALPHA * (flow / cap) ** BPR_BETA)
        dist, _ = sp(t)
        od_dist = dist[oi, di]
        od_time = {pairs[i]: float(od_dist[i]) for i in range(len(pairs))}
        for (u, v, e), f, tt in zip(edges, flow, t):
            e["flow"] = float(f); e["t"] = float(tt)
        agg: Dict[str, dict] = {}
        for (u, v, e) in edges:
            r = agg.setdefault(e["seg"], dict(seg=e["seg"], corridor=e["corridor"], cls=e["cls"], length_km=e["length"], flow=0.0, vc=0.0, time_min=0.0, t0_min=e["t0"], cap=e["cap"], n=0))
            r["flow"] += e["flow"]; r["vc"] = max(r["vc"], e["flow"] / e["cap"]); r["time_min"] += e["t"]; r["n"] += 1
        vht = vkt = 0.0
        for r in agg.values():
            r["time_min"] /= r["n"]
            r["speed_kph"] = r["length_km"] / max(r["time_min"], 1e-6) * 60
            r["level"] = level(r["vc"])
            vht += r["flow"] * r["time_min"] / 60
            vkt += r["flow"] * r["length_km"]
        demand = {pairs[i]: float(dem[i]) for i in range(len(pairs))}
        served = {k_: v for k_, v in od_time.items() if math.isfinite(v)}
        wmean = sum(demand[k_] * v for k_, v in served.items()) / max(sum(demand[k_] for k_ in served), 1e-9)
        res = {"edges": agg, "od_time": od_time, "demand": demand,
               "totals": {"vht": vht, "vkt": vkt, "avg_speed_kph": vkt / max(vht, 1e-9), "trips_per_hour": float(dem.sum()), "unserved_trips": unserved, "mean_od_time_min": wmean,
                          "severe_segments": sum(1 for r in agg.values() if r["level"] == "severe"), "moderate_segments": sum(1 for r in agg.values() if r["level"] == "moderate"),
                          "severe_km": sum(r["length_km"] for r in agg.values() if r["level"] == "severe")}}
        if use_cache and plain:
            self._cache[key] = res
        return res

    def calibrate(self, target: float = TARGET_PEAK_DELAY_RATIO, steps: int = 9):
        """Scale total demand so mean peak OD time = target x free-flow time (log-bisection)."""
        self.trip_scale = 1.0e5
        base = self.trip_scale
        self.trip_scale = base * 0.005
        free = self.assign(1.0, use_cache=False)["totals"]["mean_od_time_min"]
        lo, hi = 0.005, 3.0
        for _ in range(steps):
            mid = math.sqrt(lo * hi)
            self.trip_scale = base * mid
            ratio = self.assign(1.0, use_cache=False)["totals"]["mean_od_time_min"] / free
            if ratio > target:
                hi = mid
            else:
                lo = mid
        self.trip_scale = base * math.sqrt(lo * hi)
        self._cache.clear()

    # ---------- routing ----------
    def route(self, o: str, d: str, weight: str = "t") -> Optional[dict]:
        try:
            p = nx.shortest_path(self.G, o, d, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        return self._path_info(p)

    def _path_info(self, p: List[str]) -> dict:
        coords, segs, length, t = [], [], 0.0, 0.0
        for u, v in zip(p, p[1:]):
            e = self.G.edges[u, v]
            coords.extend(e["coords"] if not coords else e["coords"][1:])
            if not segs or segs[-1] != e["seg"]:
                segs.append(e["seg"])
            length += e["length"]; t += e["t"]
        names = []
        for s in segs:
            c = self.segments[s]["corridor"]
            if not names or names[-1] != c:
                names.append(c)
        return {"nodes": p, "segments": segs, "length_km": round(length, 2), "time_min": round(t, 1), "via": names,
                "geometry": {"type": "LineString", "coordinates": coords}}

    def k_routes(self, o: str, d: str, k: int = 3, weight: str = "t") -> List[dict]:
        """Up to k distinct alternatives by iterative edge penalisation (fast; Yen's algorithm explodes on big graphs)."""
        out, seen, pen = [], set(), {}
        G = self.G
        for _ in range(k * 4):
            try:
                path = nx.shortest_path(G, o, d, weight=lambda u, v, e: e[weight] * pen.get((u, v), 1.0))
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                break
            key = tuple(path)
            if key not in seen:
                seen.add(key); out.append(self._path_info(path))
                if len(out) >= k:
                    break
            for pr in zip(path, path[1:]):
                pen[pr] = pen.get(pr, 1.0) * 1.7
        return sorted(out, key=lambda r: r["time_min"])

    def cut_off_zones(self) -> set:
        """Demand zones that are not inside the largest strongly connected core of THIS (possibly degraded) network."""
        core = max(nx.strongly_connected_components(self.G), key=len)
        return {z for z in self.zone_nodes if z not in core}

    def node_ll(self, n: str) -> Tuple[float, float]:
        return self.G.nodes[n]["lon"], self.G.nodes[n]["lat"]

    def resolve_place(self, name_or_node: str) -> Optional[str]:
        if name_or_node in self.G:
            return name_or_node
        q = (name_or_node or "").lower().replace(" ", "")
        for k, (full, _, _) in RN.LOCATIONS.items():
            if q in (k.lower(), full.lower().replace(" ", "")) or (q and q in full.lower().replace(" ", "")):
                return self.zones[k]
        for k, (full, lon, lat, other) in RN.EVENT_VENUES.items():          # a venue only: its nearest junction, not a demand zone
            names = [k, full, *other]
            if q and any(q == n.lower().replace(" ", "") for n in names):
                node = self._nearest(lon, lat)
                lon2, lat2 = self.node_ll(node)
                return node if ((lon2 - lon) * 101.0) ** 2 + ((lat2 - lat) * 110.6) ** 2 <= 3.0 ** 2 else None   # within 3 km, or the network does not reach it
        return None


# ---------------- singleton ----------------
_model: Optional[NetworkModel] = None
_lock = threading.RLock()


def invalidate():
    global _model
    with _lock:
        _model = None


def get_model() -> NetworkModel:
    """Baseline network from backend.mobility.sources (cached; scenarios must call .clone())."""
    global _model
    with _lock:
        if _model is None:
            from backend.mobility import sources
            roads, inter, prov = sources.load_network()
            if not roads or not inter:
                raise RuntimeError("The road network is empty: no hosted road layer, no data/mobility/network.json.gz and no skeleton.")
            m = NetworkModel(roads, {}, inter)
            m.provenance = prov
            m.calibrate()
            _model = m
        return _model
