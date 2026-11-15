import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent.agent import GeoAIAgent  # noqa: E402
from backend.platform import Platform  # noqa: E402
from backend.tools.common import ToolContext  # noqa: E402
from config.settings import Settings  # noqa: E402


@pytest.fixture()
def platform(tmp_path):
    s = Settings(db_path=":memory:", evidence_dir=str(tmp_path / "ev"), anthropic_api_key="", arcgis_username="", arcgis_password="", citizen_reports=True, field_form=True)
    return Platform(settings=s, db_path=":memory:")


@pytest.fixture()
def platform_default(tmp_path):
    """The shipped default: the citizen-report feed is disabled."""
    s = Settings(db_path=":memory:", evidence_dir=str(tmp_path / "ev"), anthropic_api_key="", arcgis_username="", arcgis_password="")
    return Platform(settings=s, db_path=":memory:")


@pytest.fixture()
def ctx(platform):
    return ToolContext(platform, "test")


@pytest.fixture()
def agent(platform):
    return GeoAIAgent(platform)
