# PROJECT HANDOFF: GeoAI Operations Center | Riyadh

> Overview written earlier. The current state, decisions, ArcGIS account and gotchas are in `docs/NEXT_SESSION_HANDOFF.md` (read that first).

## 📌 Project Overview
The **GeoAI Operations Center** is a professional-grade geospatial intelligence platform. It implements a "Closed-Loop" operational lifecycle: **SENSE $
ightarrow$ SEE $
ightarrow$ UNDERSTAND $
ightarrow$ DECIDE $
ightarrow$ ACT $
ightarrow$ VERIFY $
ightarrow$ LEARN**.

The system replaces traditional manual GIS monitoring with a **Multi-Agent AI Crew** that monitors urban feeds, triages incidents, and coordinates field responses via **ArcGIS Online (AGOL)** and **ArcGIS Field Maps**.

---

## 🏗️ Technical Architecture

### 1. Backend (FastAPI)
- **Orchestration**: `backend/orchestration/crew.py` manages the AI agents and the autopilot loop.
- **GIS Store**: `backend/gis/store.py` provides a local SQLite system of record.
- **AGOL Adapter**: `backend/gis/agol.py` handles bi-directional synchronization with ArcGIS Online.
- **Simulation**: `backend/services/simulation.py` and `backend/services/feeds.py` generate synthetic operational data.

### 2. Frontend (Vanilla JS + ArcGIS JS SDK 4.30)
- **Home Portal**: `home.html` (role selection entry point).
- **Executive Hub**: `strategic_dashboard.html` (city overview, KPIs, map with 2D/3D, executive briefs, hotspots, printable report).
- **Operation**: `index.html` (the command center: alerts, digital crew, map, chat, simulated events, planner switch).
- **Investigator page**: `field.html`; **Classic view**: `classic.html`; `operational_dashboard.html` is hidden. All pages switch between English and Arabic (`frontend/i18n.js`, `frontend/rtl.css`).

### 3. The Data Loop
- **Local $
ightarrow$ AGOL**: The `ArcGISOnlineMirror` pushes local updates to hosted feature layers.
- **AGOL $
ightarrow$ Local**: The `pull_updates` method polls AGOL for updates submitted via **ArcGIS Field Maps**.

---

## 🤖 The Digital Crew (Agent Definitions)

| Agent | Role | Focus |
| :--- | :--- | :--- |
| **Faisal** | Executive | Strategic oversight, City Health KPIs, and P1 Escalations. |
| **Mansour** | Coordinator | Triage, incident opening, and inter-agent coordination. |
| **Sarah** | Water Specialist | Water network faults, leaks, and pressure anomalies. |
| **Abdullah** | Asset Health | Streetlight failure prediction and pole health (tilt/corrosion). |
| **Zayed** | Imagery Analyst | Satellite urban change, visual distortion (eight types) and land use vs zoning. |
| **Reem** | Impact Analyst | Service impact analysis on citizens and infrastructure. |
| **Turki** | Ops Manager | Work order creation, field dispatch, and closure. |
| **Maha** | Field Lead | Ground-truth verification and AI model calibration. |

---

## 🚀 Recent Major Implementations
- **Role-Based UI**: Executive Hub and Operation pages, in English and Arabic.
- **Bi-Directional Sync**: ArcGIS Field Maps tasks (Answer pick list, Note, Finish) and a bilingual report form, pulled every 15 s.
- **Use cases**: water leak; streetlights and poles; visual distortion (eight incident types); land-use management with change detection and urban change. Simulated events wake only their own feed.
- **Close scenario**: a confirmed fault is closed after a repair report from the field or a simulated crew (**Simulate repair**), always with the operator's approval.
- **Planner switch**: offline rules, Claude, OpenAI, Gemini, local models.
- **Cleanup**: weather feed removed; citizen reports disabled.

---

## 🛠️ Pending Tasks & Future Roadmap
1. Confirm the Field Maps Answer, Note and Finish flow on a phone; real per-investigator logins with one filtered map each.
2. Show Field Maps photos in the command center's report view.
3. Review the machine-written Arabic with a native speaker.
4. Optional: a single-page-app shell, ArcGIS Workforce / push notifications, and a real OAuth/OIDC identity provider instead of the `X-Role` header.

---

## 📂 Key File Index
- `backend/gis/schema.py`: The master data model for all layers.
- `backend/orchestration/crew.py`: The AI agent logic and autopilot loop.
- `backend/gis/agol.py`: The ArcGIS Online synchronization logic.
- `backend/api/app.py`: The REST API endpoints.
- `frontend/home.html`: The main entry point.
- `backend/agent/providers.py`, `backend/agent/ar.py`, `backend/services/i18n.py`: planner choices and Arabic.
- `backend/services/visual_types.py`: the eight visual-distortion types.
- `scripts/setup_field_maps_form.py`, `scripts/add_task_answer_action.py`: Field Maps setup (dry run by default).
