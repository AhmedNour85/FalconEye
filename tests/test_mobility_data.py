"""The mobility reference data: the skeleton network, the OpenStreetMap network file and the RCRC files."""
import json

import pytest

from backend.mobility import build_network, sources

PER_LANE = {"motorway": 1800, "arterial": 1500, "collector": 1200}


@pytest.fixture()
def skeleton():
    sources.configure(network="skeleton")
    yield sources.load_network()
    sources.configure(network="skeleton")


def test_the_skeleton_network_has_73_complete_segments(skeleton):
    roads, nodes, prov = skeleton
    assert len(roads) == len(build_network.build()["segments"]) == 73
    assert prov["source"] == "skeleton" and prov["road_features"] == 73
    for s in roads:
        assert s["id"] and s["length_km"] > 0 and s["lanes"] >= 1
        assert s["from_node"] in nodes and s["to_node"] in nodes
        assert s["geometry"]["type"] == "LineString" and len(s["geometry"]["coordinates"]) >= 2


def test_capacity_is_lanes_times_the_class_rate(skeleton):
    for s in skeleton[0]:
        assert s["capacity"] == s["lanes"] * PER_LANE[s["road_class"]]


def test_junction_positions_are_the_segment_ends(skeleton):
    roads, nodes, _ = skeleton
    s = roads[0]
    assert tuple(s["geometry"]["coordinates"][0]) == nodes[s["from_node"]]
    assert tuple(s["geometry"]["coordinates"][-1]) == nodes[s["to_node"]]


def test_the_two_copies_of_a_network_have_the_same_fingerprint(skeleton):
    roads = skeleton[0]
    assert sources.fingerprint(roads) == sources.fingerprint(list(reversed(roads)))
    changed = [dict(roads[0], lanes=roads[0]["lanes"] + 1)] + roads[1:]
    assert sources.fingerprint(changed) != sources.fingerprint(roads)


def test_an_unknown_network_mode_is_refused():
    with pytest.raises(ValueError):
        sources.configure(network="osm")


@pytest.mark.skipif(not sources.NETWORK_FILE.exists(), reason="data/mobility/network.json.gz not built (scripts/build_mobility_data.py)")
def test_the_openstreetmap_network_file_is_whole():
    raw = sources.read_network_file()
    segs = raw["segments"]
    assert len(segs) > 10000
    assert raw["attribution"] == sources.ATTRIBUTION
    ids = {s["id"] for s in segs}
    assert len(ids) == len(segs)
    for s in segs:
        assert s["length_km"] > 0 and s["lanes"] >= 1 and len(s["coords"]) >= 2 and s["from_node"] != s["to_node"]
        assert s["road_class"] in PER_LANE
    # the headline road of the demo is there under the name the closure request uses
    assert any(s["corridor"] == "Olaya Street" for s in segs)
    assert any(s["corridor"] == "King Fahd Road" for s in segs)


@pytest.mark.skipif(not sources.RCRC_DIR.exists(), reason="data/mobility/rcrc not built")
def test_the_rcrc_files_have_the_published_counts_and_a_notice():
    counts = {n: len(sources.rcrc(n)["features"]) for n in ("metro_lines", "metro_stations", "bus_routes", "bus_stops")}
    assert counts == {"metro_lines": 6, "metro_stations": 94, "bus_routes": 117, "bus_stops": 3010}
    notice = (sources.DATA / "NOTICE.md").read_text(encoding="utf-8")
    assert "KSA Open Data License" in notice and "ODbL" in notice


def test_a_missing_rcrc_file_is_none_not_an_error():
    assert sources.rcrc("tram_lines") is None


def test_hospitals_come_from_the_reference_list_when_there_is_no_hosted_layer(skeleton):
    hs = sources.list_hospitals()
    assert len(hs) == 8 and all(h["geometry"]["type"] == "Point" for h in hs)
    assert {f["kind"] for f in sources.reference_facilities()} == {"hospital", "civil_defense", "ems"}


def test_the_scenario_archive_keeps_only_the_latest_results():
    for i in range(sources.ARCHIVE_LIMIT + 5):
        sources.upsert_many("ArchiveTest", [{"id": f"x-{i}", "n": i}])
    kept = sources.list_("ArchiveTest")
    assert len(kept) == sources.ARCHIVE_LIMIT and kept[-1]["n"] == sources.ARCHIVE_LIMIT + 4
    assert sources.get("ArchiveTest", "x-0") is None
    assert json.dumps(kept)  # plain data
