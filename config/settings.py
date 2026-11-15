"""Central configuration. All secrets come from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: str = ""           # optional: lets the Operation page switch to OpenAI without typing a key (OPENAI_API_KEY)
    google_api_key: str = ""           # optional: Google Gemini (GOOGLE_API_KEY or GEMINI_API_KEY)
    planner: str = ""                  # planner at start-up: rules | claude | openai | google | lmstudio | ollama | hermes | custom (GEOAI_PLANNER); empty = Claude if a key exists, else rules
    arcgis_url: str = "https://www.arcgis.com"
    arcgis_username: str = ""
    arcgis_password: str = ""
    arcgis_js_api_key: str = ""
    arcgis_layer_prefix: str = "CityView"   # hosted layers are titled <prefix>_<layer>; "GeoAIOps" (the Agentic_AI_City project's layers) is refused
    store: str = "memory"              # where the records live: "arcgis" (ArcGIS Online, the system of record) or "memory" (tests and development; nothing is kept).
                                       # load_settings() defaults to "arcgis" (GEOAI_STORE); a Settings() built by hand, as the tests do, is "memory".
    seed: int = 20260101
    field_form: bool = False           # the in-app investigator form is disabled; field teams use ArcGIS Field Maps (GEOAI_FIELD_FORM=1 re-enables it)
    field_users: dict | None = None    # worker id -> ArcGIS Online username used in Field Maps, e.g. GEOAI_FIELD_USERS=WRK-001=nawaf.harbi,WRK-002=khalid.otaibi
    field_sync_seconds: float = 15.0   # how often reports made in Field Maps are pulled from ArcGIS Online
    citizen_reports: bool = False      # the citizen-report feed is disabled unless GEOAI_CITIZEN_REPORTS=1
    field_lang: str = "en"             # language of the task text on the phone: en | ar | both (GEOAI_FIELD_LANG)

    @property
    def arcgis_enabled(self) -> bool:
        return bool(self.arcgis_username and self.arcgis_password)

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


class ConfigError(ValueError):
    """The configuration would be unsafe or cannot work. The app does not start."""


REFUSED_PREFIXES = ("geoaiops",)       # the hosted layers of the Agentic_AI_City project: this app must never write to them


def check_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p or p.lower() in REFUSED_PREFIXES:
        raise ConfigError(f"ARCGIS_LAYER_PREFIX={prefix!r} is refused: 'GeoAIOps' is the layer prefix of the Agentic_AI_City project, and an empty prefix is not allowed. "
                          "Riyadh City View uses 'CityView'.")
    return p


def load_settings() -> Settings:
    e = os.environ.get
    store = e("GEOAI_STORE", "arcgis").strip().lower()
    if store not in ("arcgis", "memory"):
        raise ConfigError(f"GEOAI_STORE={store!r}: use 'arcgis' (ArcGIS Online is the system of record) or 'memory' (tests and development; nothing is kept)")
    return Settings(
        anthropic_api_key=e("ANTHROPIC_API_KEY", ""),
        anthropic_model=e("ANTHROPIC_MODEL", "claude-opus-5-5"),
        openai_api_key=e("OPENAI_API_KEY", ""),
        google_api_key=(e("GOOGLE_API_KEY", "") or e("GEMINI_API_KEY", "")),
        planner=e("GEOAI_PLANNER", ""),
        arcgis_url=e("ARCGIS_URL", "https://www.arcgis.com"),
        arcgis_username=e("ARCGIS_USERNAME", ""),
        arcgis_password=e("ARCGIS_PASSWORD", ""),
        arcgis_js_api_key=e("ARCGIS_JS_API_KEY", ""),
        arcgis_layer_prefix=check_prefix(e("ARCGIS_LAYER_PREFIX", "CityView")),
        store=store,
        seed=int(e("GEOAI_SEED", "20260101")),
        citizen_reports=e("GEOAI_CITIZEN_REPORTS", "").lower() in ("1", "true", "yes"),
        field_form=e("GEOAI_FIELD_FORM", "1").lower() in ("1", "true", "yes"),       # the in-app investigator page is on next to ArcGIS Field Maps
        field_users={k.strip(): v.strip() for k, _, v in (p.partition("=") for p in e("GEOAI_FIELD_USERS", "").split(",")) if k.strip() and v.strip()},
        field_sync_seconds=float(e("GEOAI_FIELD_SYNC_SECONDS", "15")),
        field_lang=(e("GEOAI_FIELD_LANG", "en").strip().lower() if e("GEOAI_FIELD_LANG", "en").strip().lower() in ("en", "ar", "both") else "en"),
    )
