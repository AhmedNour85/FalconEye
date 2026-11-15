# GeoAI Operations Center | Riyadh
## Project Explanation & Review

The **GeoAI Operations Center (Riyadh)** is a state-of-the-art agentic AI platform designed for urban geospatial operations. It implements a continuous operational loop that bridges the gap between digital sensing and real-world verification.

### 🌟 Core Vision
**"One Agent, One Geospatial Platform, One Lifecycle"**
The system doesn't just detect problems; it manages the entire journey from the first sensor anomaly to the final field-verified repair and the subsequent calibration of the AI model.

---

### 🔄 The Operational Lifecycle
The platform operates on a 7-stage recursive loop:

1. **SENSE**: Monitoring IoT water sensors, streetlight and pole telemetry (citizen reports exist but are switched off).
2. **SEE**: Analyzing satellite imagery for urban change, visual distortion (eight street-level problem types) and land-use violations.
3. **UNDERSTAND**: Using GeoAI for feature extraction and spatial analysis to determine the "what" and "where".
4. **DECIDE**: A multi-agent crew triages findings, ranks incidents by severity, and creates executive briefs.
5. **ACT**: Proposing work orders and dispatching field crews (requires **Human Approval**).
6. **VERIFY**: Field investigators confirm findings in ArcGIS Field Maps (Answer, Note, Finish, or the report form with GPS and photos).
7. **LEARN**: Comparing AI predictions vs. field reality to calibrate detection thresholds.

---

### 🤖 The Digital Crew (Multi-Agent System)
Unlike a single chatbot, this system uses a specialized crew of AI agents, each with a specific role:

| Agent | Role | Responsibility |
| :--- | :--- | :--- |
| **Faisal** | Executive | Escalation, high-level briefs, and strategic oversight. |
| **Mansour** | Coordinator | Triage, incident opening, and inter-agent coordination. |
| **Sarah** | Water Specialist | Monitoring and analyzing water network faults. |
| **Abdullah** | Asset Health | Streetlight failure prediction and pole health. |
| **Zayed** | Imagery Analyst | Satellite comparison: urban change, visual distortion, land use vs zoning. |
| **Reem** | Impact Analyst | Assessing the service impact on citizens and infrastructure. |
| **Turki** | Ops Manager | Work order creation, dispatch, and closure. |
| **Maha** | Field Lead | Verification of ground truth and learning feedback. |

---

### 🛠 Technical Architecture

#### Stack
- **Frontend**: Vanilla JavaScript + ArcGIS Maps SDK 4.30 (No build step, high performance).
- **Backend**: FastAPI (Python) providing a REST API for the UI and Agent.
- **Intelligence**: a planner chosen on the Operation page: Claude, OpenAI, Gemini, a local model (LM Studio, Ollama, Hermes) or any OpenAI-compatible server; the offline rule planner needs no key and answers in English or Arabic.
- **Data**: SQLite (Local Feature Store) with an optional write-through mirror to ArcGIS Online.
- **GIS**: Real OpenStreetMap (OSM) data for Riyadh roads and buildings.

#### Key Technical Features
- **Human-in-the-Loop**: The AI cannot execute "Act" tools (dispatch/close) directly. It creates a `Proposed` state that a human operator must approve.
- **GeoAI Processing**: Implements real z-score anomaly detection for leaks and morphological analysis for satellite imagery.
- **English and Arabic**: every page switches between English and right-to-left Arabic; backend sentences are translated on request (`docs/PROJECT_DOCUMENTATION.md`, section 13).
- **Closed-Loop Learning**: The system records "False Positives" from the field and uses them to adjust the calibration multipliers for future detections.

---

### 🖼 Visual Guide & Documentation

#### 1. Architecture Diagram
A detailed map of the data flow from the Browser UI $\rightarrow$ FastAPI $\rightarrow$ GeoAI Agent $\rightarrow$ Tool Registry $\rightarrow$ Feature Store.
👉 **View here:** `docs/architecture_diagram.html`

#### 2. Lifecycle Diagram
A visual representation of the SENSE $\rightarrow$ LEARN loop and the feedback mechanisms.
👉 **View here:** `docs/lifecycle_diagram.html`

#### 3. UI Screen Overviews
- **NCCC (Command Center)**: A unified dashboard featuring a live map of incidents, a notification feed of agent findings, and the "Digital Crew" status.
- **Field Maps and the Investigator page**: investigators work in ArcGIS Field Maps (tasks, an Answer pick list, a bilingual report form with GPS and photos); `field.html` is an optional in-app version.
- **Imagery Swipe Viewer**: A specialized tool for comparing two different satellite epochs (dates) with AI-detected change polygons overlaid.

---

### 🚀 Quick Start
1. **Install**: `pip install -r requirements.txt`
2. **Run**: `python -m backend.main`
3. **Access**: Open `http://127.0.0.1:8000` in your browser.
4. **Demo**: Use the "Simulate an event" menu to trigger one use case and watch the crew react; approve, then use "Simulate repair" to take a confirmed fault to closure. See `docs/demo_script.md`.
