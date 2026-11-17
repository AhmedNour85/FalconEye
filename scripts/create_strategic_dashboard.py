"""Create the ArcGIS Dashboards version of the Strategic Dashboard (a NEW item; the original page and every existing item are left alone).

    python scripts/create_strategic_dashboard.py            # DRY RUN: reads the CityView layers, prints the dashboard definition, writes nothing
    python scripts/create_strategic_dashboard.py --apply    # creates ONE new private dashboard item titled CityView Strategic Dashboard

The dashboard reads the CityView_* hosted layers (incidents, work orders, verification). It is private to the signed-in account.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402

TITLE = "CityView Strategic Dashboard"
TAGS = "CityView-Riyadh,SYNTHETIC-DEMO,Falcon Eye"
SUMMARY = "Falcon Eye strategic overview of operational incidents (synthetic demo data)."


class _AsLayerItem:
    """The Python API's chart widgets look for a table on the item to learn the id field; our hosted layers are layers, so say so."""

    def __init__(self, item):
        self._item = item
        self.tables = [item.layers[0]]

    def __getattr__(self, name):
        return getattr(self._item, name)


def build(incidents, work_orders, verification):
    """The dashboard object for the three layer items (pure: no network, no writes). Everything is unfiltered, so it works the same on any data."""
    from arcgis.apps import dashboard as D

    dash = D.Dashboard()
    dash.theme = "dark"
    dash.header = D.Header(title="Falcon Eye · عيون الصقر", subtitle="Strategic Dashboard · لوحة القيادة الاستراتيجية", size="medium")
    inc = _AsLayerItem(incidents)
    kpis = [D.Indicator(incidents, name="Incidents", layer=0, title="Incidents · الحوادث"),
            D.Indicator(work_orders, name="WorkOrders", layer=0, title="Work orders · أوامر العمل"),
            D.Indicator(verification, name="Verified", layer=0, title="Field reports · التقارير الميدانية")]
    def chart(cls, name, field, title):
        c = cls(inc, name=name, layer=0, categories_from="groupByValues", title=title)
        c.data.category_field = field
        c.data.statistic = "count"
        return c

    charts = [chart(D.PieChart, "Severity", "Severity", "By severity · حسب الخطورة"), chart(D.PieChart, "Status", "Status", "By status · حسب الحالة"),
              chart(D.PieChart, "Type", "Incident_Type", "By type · حسب النوع"), chart(D.PieChart, "Area", "Area_Name", "By area · حسب المنطقة")]
    latest = D.List(incidents, name="Latest", layer=0, title="Incidents · الحوادث")
    dash.layout = D.add_row([D.add_column(kpis), D.add_column(charts[:2]), D.add_column(charts[2:] + [latest])])
    return dash


def main(argv=None, gateway=None, settings=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--title", default=TITLE)
    args = ap.parse_args(argv)
    if settings is None:
        from config.settings import load_settings
        settings = load_settings()
    if not settings.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first.")
    prefix = settings.arcgis_layer_prefix
    if not args.title.startswith(prefix):
        sys.exit(f"Refused: the title {args.title!r} must start with {prefix!r}. This project only creates its own items.")
    if gateway is None:
        from backend.gis.agol import ArcGISGateway
        gateway = ArcGISGateway(settings)
    gis = gateway.gis
    existing = [i for i in gis.content.search(f'title:"{args.title}" AND owner:{gis.users.me.username}', item_type="Dashboard")]
    if existing:
        sys.exit(f"Refused: a dashboard titled {args.title!r} already exists ({existing[0].id}). Nothing was changed.")
    dash = build(gateway._item(S.INCIDENTS), gateway._item(S.WORK_ORDERS), gateway._item(S.VERIFICATION))
    print(json.dumps(dash._convert_to_json(), indent=1, ensure_ascii=False, default=str)[:6000])
    if not args.apply:
        print("\nDRY RUN: nothing was written. Re-run with --apply to create the new private dashboard item.")
        return 0
    item = dash.save(args.title, summary=SUMMARY, tags=TAGS, gis=gis)
    print("Created:", item.id if hasattr(item, "id") else item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
