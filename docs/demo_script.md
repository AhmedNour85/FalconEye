# Executive demonstration script (~10 minutes)

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
