# Mobility reference data

Built by `scripts/build_mobility_data.py` on 2026-11-15 from the files of the `Agentic_AI_Transportation` project.

| File | Rows | Source | Licence |
|---|---|---|---|
| `network.json.gz` | 10,986 road segments, 7,939 junctions | OpenStreetMap, main roads only (motorway to secondary, with their ramps) | ODbL. Credit: © OpenStreetMap contributors (ODbL) |
| `rcrc/metro_lines.geojson` | 6 | RCRC open data | KSA Open Data License |
| `rcrc/metro_stations.geojson` | 94 | RCRC open data | KSA Open Data License |
| `rcrc/bus_routes.geojson` | 117 | RCRC open data | KSA Open Data License |
| `rcrc/bus_stops.geojson` | 3,010 | RCRC open data | KSA Open Data License |

RCRC is the Royal Commission for Riyadh City. Licence text: https://open.data.gov.sa/odp-public/static/en/assets/Open_Data_License_En.pdf. The files were retrieved on 2026-11-13.
Credit to show wherever this data is displayed: "Source: Royal Commission for Riyadh City (RCRC) open data, KSA Open Data License".

Not in these files: hospital and emergency-station positions. Those are approximate reference positions kept in
`backend/mobility/riyadh_network.py`, and bed counts are placeholders.

Traffic volumes and speeds are not data. The model calculates them from this network and a synthetic demand profile.
