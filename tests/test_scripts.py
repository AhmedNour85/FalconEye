"""The account scripts: dry run by default, no secrets on screen, no default that points at another project's items."""
from types import SimpleNamespace

import pytest

from backend.gis import schema as S
from config.settings import Settings
from scripts import add_task_answer_action, create_feature_layers, initialize_demo, make_env, setup_field_maps_form
from scripts._guard import own_item_or_exit
from tests.fakes import FakeGateway

OTHER_ENV = ("ANTHROPIC_API_KEY=sk-should-not-be-copied\nARCGIS_URL=https://www.arcgis.com\nARCGIS_USERNAME=someone\n# ARCGIS_PASSWORD=commented-out\n"
             "ARCGIS_PASSWORD=s3cret=with=equals\nARCGIS_LAYER_PREFIX=GeoAIOps\nGEOAI_DB_PATH=data/geoai.sqlite\nGEOAI_FIELD_USERS=WRK-001=story_viewer\n")


def test_make_env_copies_only_the_three_arcgis_lines_and_prints_no_value(tmp_path, capsys):
    src = tmp_path / "src.env"
    src.write_text(OTHER_ENV, encoding="utf-8")
    out = tmp_path / ".env"
    assert make_env.main([str(src), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "ARCGIS_USERNAME=someone" in text and "ARCGIS_PASSWORD=s3cret=with=equals" in text and "ARCGIS_URL=https://www.arcgis.com" in text
    assert "ARCGIS_LAYER_PREFIX=CityView" in text and "GEOAI_STORE=arcgis" in text
    assert "ARCGIS_LAYER_PREFIX=GeoAIOps" not in text and "GEOAI_DB_PATH" not in text and "sk-should-not-be-copied" not in text and "story_viewer" not in text
    shown = capsys.readouterr().out
    assert "s3cret" not in shown and "someone" not in shown and "ARCGIS_PASSWORD" in shown


def test_make_env_refuses_to_overwrite_an_existing_env(tmp_path, capsys):
    src = tmp_path / "src.env"
    src.write_text(OTHER_ENV, encoding="utf-8")
    out = tmp_path / ".env"
    out.write_text("KEEP=me\n", encoding="utf-8")
    assert make_env.main([str(src), "--out", str(out)]) == 3 and out.read_text(encoding="utf-8") == "KEEP=me\n"


def test_make_env_writes_nothing_when_the_source_has_no_sign_in(tmp_path):
    src = tmp_path / "src.env"
    src.write_text("ARCGIS_USERNAME=someone\nARCGIS_PASSWORD=\n", encoding="utf-8")
    out = tmp_path / ".env"
    assert make_env.main([str(src), "--out", str(out)]) == 4 and not out.exists()


def test_field_map_scripts_have_no_default_web_map():
    for mod in (setup_field_maps_form, add_task_answer_action):
        with pytest.raises(SystemExit):
            mod.main([])                                        # --webmap is required
        assert "07fb979378b94c91ab463d8c17601bd0" not in open(mod.__file__, encoding="utf-8").read()
        assert "e1e83bef0e2247de9dafac88d5a1031b" not in open(mod.__file__, encoding="utf-8").read()


def test_a_web_map_without_the_prefix_or_owned_by_someone_else_is_refused():
    city_map = SimpleNamespace(title="GeoAI Field Maps - Investigator Map", owner="story_viewer")
    with pytest.raises(SystemExit, match="does not carry the 'CityView' prefix"):
        own_item_or_exit(city_map, "CityView", "07fb", "story_viewer")
    with pytest.raises(SystemExit, match="owned by someone.else"):
        own_item_or_exit(SimpleNamespace(title="CityView Field Maps", owner="someone.else"), "CityView", "abc", "story_viewer")
    with pytest.raises(SystemExit, match="no item"):
        own_item_or_exit(None, "CityView", "abc", "story_viewer")
    ours = SimpleNamespace(title="CityView Field Maps - Investigator Map", owner="story_viewer")
    assert own_item_or_exit(ours, "CityView", "abc", "story_viewer") is ours


class PlanGateway(FakeGateway):
    owner = "city.owner"

    def __init__(self):
        super().__init__()
        self.created = []

    def create_layers(self, only=None, dry_run=True):
        plan = [{"layer": n, "title": self.title(n), "action": "create", "fields": list(d.fields)} for n, d in S.LAYERS.items() if not only or n in only]
        if not dry_run:
            self.created += [p["title"] for p in plan]
        return plan


def test_create_feature_layers_is_a_dry_run_unless_told_to_apply(capsys):
    gw = PlanGateway()
    assert create_feature_layers.main([], gateway=gw) == 0 and gw.created == []
    shown = capsys.readouterr().out
    assert "DRY RUN (nothing is changed)" in shown and "CityView_Riyadh_Work_Orders" in shown and "Run again with --apply" in shown
    assert create_feature_layers.main(["--apply", S.WORKERS], gateway=gw) == 0 and gw.created == ["CityView_Riyadh_Field_Workers"]


def test_initialize_demo_dry_run_writes_nothing_and_says_what_it_would_delete(capsys):
    gw = PlanGateway()
    gw.outside_edit(S.WORKERS, {"Worker_ID": "WRK-OLD"})
    assert initialize_demo.main([], gateway=gw, settings=Settings()) == 0
    shown = capsys.readouterr().out
    assert gw.writes == [] and "DRY RUN (nothing is changed)" in shown and "would DELETE 1 row(s)" in shown
    assert len(gw.rows(S.WORKERS)) == 1


def test_initialize_demo_apply_fills_the_hosted_layers_and_gives_the_lock_back(capsys):
    gw = PlanGateway()
    gw.outside_edit(S.WORKERS, {"Worker_ID": "WRK-OLD"})
    assert initialize_demo.main(["--apply"], gateway=gw, settings=Settings()) == 0
    ids = gw.ids(S.WORKERS)
    assert "WRK-OLD" not in ids and "WRK-001" in ids and len(gw.rows(S.SENSORS)) >= 1000
    assert "server.lock" not in gw.ids(S.CONFIG)                    # the app can start straight after
    assert "The demo data is in ArcGIS Online" in capsys.readouterr().out
