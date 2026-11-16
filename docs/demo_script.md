# Riyadh City View demo script

## Two-minute walk-through (headline story, then one city story, then Arabic)

Start: `python -m backend.main`, open http://127.0.0.1:8000/index.html (Operation page). Wait until the strip under the title says the traffic model is ready (about a minute after start).

**1. Water leak that touches a road (about 70 seconds)**
1. Simulate an event: **Water leak**. The crew detects a *suspected* leak (Olaya) and raises an alert. Point at the **lifecycle strip** on the alert: Detected, Analysed, Proposed, Approved, Dispatched, Verified, Resolved.
2. Within a minute the alert gains a **road-impact line**: closing 2 lanes of the nearest road by day against by night, in trip-hours and minutes to the worst hospital. Say: "Modelled, not measured."
3. **Approve** the work-order proposal. One approval records the work order and the planned closure. Open **Compare strategies** on the closure alert: five responses, one recommended, assumptions listed.
4. Nothing was carried out before the click. Everything on screen came from a Python tool.

**2. A city-service story (about 30 seconds)**
1. Simulate an event: **Streetlight & pole monitoring**. Approve the work order, then the field assignment. The task is in ArcGIS Field Maps for the investigator.
2. **Simulate repair**, approve the closure. The incident is Resolved and the calibration updates.

**3. Arabic and the Hub (about 20 seconds)**
1. Press **العربية**. Ask the crew: `ماذا يحدث لو أُغلق طريق الملك فهد غدا من 8 إلى 4؟` The answer is in Arabic, with the Modelled label.
2. Open the **Executive Hub**: the four mobility numbers, the trend line, congestion hotspots. **Daily brief (PDF)**: English or Arabic, one page.

Questions to try in Ask the crew (English or Arabic): "What if demand grows 20% near KAFD?", "What will an event at KAFD with 40,000 people do to traffic?", "How long does it take to reach a hospital?", "Which roads need maintenance first?", "How is the traffic right now?". Questions create information only; they never create an approval.

Notes: the live record holds earlier demo rows (INC-0037, CLS-0002, SCN-0004, WO-0026, VER-0025). **Reset demo** empties and refills the `CityView` demo layers; run it only when you mean to.

---

# Longer walk-through of the city-service use cases (~10 minutes)

## Current flow on the Operation page (recommended)

1. `python -m backend.main` → http://127.0.0.1:8000 → **Operation** → **Reset demo** (the cards read 0 waiting / 0 open / 0 critical / 0 resolved). Use the **EN / العربية** button to show either language.
2. **Simulate an event**: Water leak, Streetlight & pole monitoring, Visual distortion detection (three of the eight visual types appear) or Land-use management (violations plus urban change). Only that use case reacts; the crew panel shows who did what.
3. **Approve** the work-order proposal, then the crew recommendation (who to send). The task appears in ArcGIS Field Maps for the investigator.
4. The investigator answers on the phone (Answer, Note, Finish, or the report form); or switch on **Simulated crew auto-responds**. The "Fault confirmed on site" alert arrives with **View report**.
5. If no repair report exists yet, press **Simulate repair** (a clearly labelled simulated crew), then **Approve** the closure: the incident is Resolved and the model calibration is updated.
6. Optional: the planner icon switches the chat between the offline planner, Claude, OpenAI, Gemini or a local model; **Compare imagery** and the **Urban change** layer show the satellite comparison; the **Executive Hub** shows city overview, hotspots and the printable daily report.

## Guided Demo (classic view, ~10 minutes)

Start: `python -m backend.main` → http://127.0.0.1:8000 → **Guided Demo** tab → **Reset demo**. Watch the lifecycle bar at the top light up stage by stage.
Use the *auto-approve* box for a hands-free replay, or leave it off and click **Approve** yourself (stronger message).

| Scene | Say | Click / type | What the audience sees |
|---|---|---|---|
| 1 SENSE | "A pressure sensor in Olaya just dropped 28%." | Run scene 1 | Sensor event → synthetic pipeline → *suspected* leak, risk score, probable position on the real OSM map |
| 2 SEE | "Now the city itself: two imagery epochs." | Run scene 2 | Before/after (simulated) → change candidates; vegetation-only differences held back as possibly seasonal |
| 3 UNDERSTAND | "From pixels to meaning." | Run scene 3 | Buildings/roads extracted, assets and facilities within radius - numbers come from tools, not the LLM |
| 4 DECIDE | "What matters most?" | Run scene 4 | Incidents created, KPIs recomputed, hotspots, ranked list with evidence |
| 5 ACT | "Intelligence becomes action - with a human in the loop." | Run scene 5 → approve in panel → run again | Work-order proposal, nothing exists until approval; team recommended by skill, distance, workload |
| 6 VERIFY | "Reality check." | Run scene 6 (or Field Worker Portal → submit with photo/GPS) | Field evidence compared with the AI finding → Confirmed |
| 7 LEARN | "The loop closes." | Run scene 7 | Repair, closure approval, precision/calibration updated (no model retraining) |
| + Streetlights | "Same agent, different asset class." | Run scene 8 | King Fahd Road cluster of *predicted* failures → incident → work order → inspection |

Free-form: open **AI Copilot** and type the prompts in `docs/agent_tools.md` — the conversation keeps incident context ("that one").

Talking points: ArcGIS Online is the system of record (hosted layers); the agent orchestrates but never calculates; every action is audited; synthetic vs. real data is labelled everywhere.
Replay: **Reset demo** (regenerates from the seed, ~2 s).
