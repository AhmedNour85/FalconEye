# Riyadh City View: design

Date: 2026-11-15. Status: **approved by you on 2026-11-15 (revision 4), with every proposed default accepted**.

Revision 2 (2026-11-15): at your request the project now uses ArcGIS Online with the layer prefix `CityView`, and ArcGIS Field Maps tasks. Sections 2, 4, 7, 9, 10, 11 and 12 changed, and section 7 has a new part, "ArcGIS Online and Field Maps".

Revision 3 (2026-11-15): at your request the ArcGIS agentic developer toolkit is part of the plan. Section 13 is new. Sections 7, 10 and 12 changed.

Revision 4 (2026-11-15): at your request ArcGIS Online is the system of record and there is no local database. The background write queue is removed. Sections 2, 3, 7, 8, 9, 10, 11, 12 and 13 changed.

Items marked **[Your decision]** need a yes or a correction from you. Items marked **[My call]** are choices I made that you can overrule.

## 1. What this is and why

Riyadh City View is one command center for Riyadh that covers city services and mobility together. It keeps the concept and workflow of `Agentic_AI_City` and adds what `Agentic_AI_Transportation` can do.

It is for two people, mainly as a demo: a command-center operator and an executive. This audience is my guess, which you accepted.

The reason to combine the two apps is the link between them. A city-service problem often becomes a traffic problem, and today nobody sees both in one place.

**The headline story:**

1. Sarah detects a water leak on Olaya Street.
2. Mansour opens an incident. Reem sizes the impact on nearby facilities.
3. Turki prepares a repair work order. The repair needs two lanes closed.
4. Noura simulates the closure and compares a daytime window with a night window.
5. The alert shows the road impact and the recommended window. The operator approves once.
6. An investigator verifies on site. Maha compares the result with the prediction.

## 2. Goals, non-goals and anti-goals

### Goals

- One app, one system of record, one digital crew and one lifecycle: Sense → See → Understand → Decide → Act → Verify → Learn.
- Seven use cases: the four city-service ones from the City project, unchanged, plus three mobility ones.
- A road-impact assessment on repair work that needs road space, before the operator approves it.
- English and Arabic on every page, right-to-left in Arabic.
- ArcGIS Online is the system of record. All data is stored in hosted layers under the prefix `CityView`. There is no local database.
- Investigators work in ArcGIS Field Maps tasks.

### Non-goals for the first version

| Left out | Where it exists today | Why |
|---|---|---|
| Custom AI agent builder, agent teams, usage log | Transportation | Not part of the City concept |
| AI provider wizard with encrypted key storage | Transportation | The City planner switch stays; keys stay in memory only |
| Live traffic overlay (TomTom, ArcGIS World Traffic) | Transportation | Needs paid keys; never verified with one |
| ArcGIS sign-in for private layers in the browser | Transportation | The server signs in; the browser gets its data from the app |
| SUMO adapter, new-infrastructure scenario, saved-scenario comparison page | Transportation | Not needed for the three mobility use cases |
| Separate pages for Infrastructure Health, Road Safety, Planning | Transportation | Their answers are reachable through "Ask the crew" |
| `classic.html`, `operational_dashboard.html`, guided demo | City | Legacy or hidden pages **[Your decision]** |

### Anti-goals

These would make the project a failure even if it runs:

- Two apps glued together with two crews and two looks.
- A number on screen that came from a language model and not from a Python tool.
- Any action carried out without a person's approval.
- Any change to an ArcGIS Online item that does not carry the `CityView` prefix, or any write to the two source folders.
- Modelled or synthetic data shown as if it were live.
- A local database, or any record kept only on this computer.

## 3. Approaches considered

| Option | What it means | Trade-off |
|---|---|---|
| **A. Copy City, port mobility into it (chosen)** | One app, one system of record, one crew | Most porting work; stays true to the City concept |
| B. A thin shell over both apps | Both backends run side by side | Fast; two crews, two databases, weak combined story |
| C. Start from Transportation and restyle it | Keeps every mobility feature | Works against "be like `Agentic_AI_City`" |

You picked option A on 2026-11-15.

## 4. What the user sees

### Pages

| Page | Change from the City project |
|---|---|
| Home portal | New title "Riyadh City View". Same two cards: Executive Hub and Operation. |
| Operation | Same layout. Additions are listed below. |
| Executive Hub | Mobility numbers, traffic and transit layers, and a daily brief download. |
| Investigator page | Stays on next to Field Maps, as you decided in the City project. Three new task types for the traffic field team. |
| ArcGIS Field Maps (phone) | The main field channel: tasks with Finish, Answer, Note and Attach, and the bilingual report form. |

### Operation page

```
[ Waiting for decision ] [ Open incidents ] [ Critical ] [ Resolved ]
+--------------------------+-----------------------------------------+
| Digital crew (11)        |  Map                                    |
|  Faisal   Mansour        |   layers: Traffic, Metro, Bus,          |
|  Sarah  Abdullah  Zayed  |   Hospitals, Closures, Urban change     |
|  Reem   Turki     Maha   |   hour slider when Traffic is on        |
|  Nasser Noura     Fahad  |   2D / 3D                               |
| Alerts: Needs action|All |  Ask the crew...                        |
|  [lifecycle strip]       |                                         |
|  Road impact: ...        |                                         |
|  [Approve] [Reject]      |                                         |
+--------------------------+-----------------------------------------+
[Water][Lights][Imagery][Distortion][Land use][Traffic][Closures & events]
```

What is new on this page:

- **Crew panel:** eleven agents. Faisal and Mansour stay on the first row, then three per row.
- **Simulate an event menu:** two groups **[Your decision]**. You had fixed this menu at four flat options.
  - City services: Water leak, Streetlight & pole monitoring, Visual distortion detection, Land-use management.
  - Mobility: Traffic incident, Road closure, Major event.
- **Map layers:** checkboxes for Traffic, Metro, Bus, Hospitals and Planned closures, next to the existing Urban change checkbox. All start off except incidents. An hour slider appears when Traffic is on.
- **Feed cards:** two new cards, Traffic (Nasser) and Closures & events (Noura).
- **Alerts:**
  - A lifecycle strip of seven steps on each alert, with the current step highlighted.
  - A road-impact line on repair alerts (section 6).
  - A "View impact on map" button that draws the closed section, the congested segments and the detour routes.
  - A "Compare strategies" button on closure alerts. It opens a table of the five response strategies with the recommended one highlighted.

The four key numbers, the alert tabs, the bell, the planner switch, Reset demo and the language button stay as they are.

### Executive Hub

- **City Overview** gains four mobility numbers: peak delay ratio, severe road segments, worst hospital access time and planned closures.
- **Map layer toggles** gain Traffic and Metro.
- **Executive Briefs** gains "Download daily brief" as a PDF in English or Arabic.
- **Hotspots strip** includes congestion hotspots.

## 5. The digital crew

The eight City agents keep their names, roles and tools. Three mobility specialists join **[Your decision: names]**.

| Agent | Role | What it does | Transportation agents folded in |
|---|---|---|---|
| **Nasser** | Traffic GeoCoworker | Watches the traffic state and road incidents | Monitoring, prediction, traffic optimization |
| **Noura** | Mobility Simulation GeoCoworker | Simulates closures, events and demand; compares response strategies; checks hospital access | Simulation, transportation planning, emergency resilience |
| **Fahad** | Road Safety & Assets GeoCoworker | Adds accident history and road-asset condition to mobility findings; ranks maintenance priority | Safety risk, infrastructure health |

The other two Transportation agents map onto existing crew members: resource optimization to Turki, executive intelligence to Faisal.

The names do not clash with the investigators (Nawaf, Khalid, Saad, Hamad, Yousef, Ibrahim, Majed). A new field team, Traffic Response, gets two investigators with new names.

## 6. Use cases and workflow

### The four city-service use cases

Water leak, streetlights and poles, visual distortion and land-use management work exactly as in the City project.

### The three mobility use cases

| Lifecycle step | Traffic incident | Road closure | Major event |
|---|---|---|---|
| Sense | Nasser sees a blocked-lane report and abnormal congestion | A closure request arrives | An event notice arrives (place, attendance, hours) |
| Understand | Noura estimates delay, affected segments and hospital access. Fahad adds accident history. | Noura runs five response strategies | Noura simulates the extra demand |
| Decide | Mansour opens an incident. Faisal escalates if Critical. | Same, with a recommended strategy | Same, with a traffic management plan |
| Act | Turki proposes a traffic response and a field dispatch | Turki proposes the recommended closure plan | Turki proposes the plan |
| Approval | Operator approves or rejects | Operator approves or rejects | Operator approves or rejects |
| Verify | Investigator confirms the road is clear | Investigator confirms the closure is in place | Investigator confirms the plan is in place |
| Learn | Maha records confirmed or not found, which feeds the same accuracy numbers as the other use cases | Same | Same |

The five response strategies come from the Transportation project: do nothing, reschedule to night, diversion with signal retiming, demand shift, and combined. Their effects are stated assumptions and are listed with every result.

An approved plan is only a record. Nothing controls signals, signs or dispatch systems.

### The cross-domain link

When Turki prepares a work order for a water-leak incident within 60 m of a modelled road, the crew adds a road-impact step:

1. Noura simulates the lane closure in a daytime window and in a night window.
2. The alert gains one line. With made-up numbers, it reads: "Road impact: closing 2 lanes of Olaya Street 08:00 to 16:00 adds 1,200 trip-hours and 4 min to the worst hospital access; at night 150 trip-hours and 1 min. Recommended: night."
3. The recommended window is stored with the work-order proposal. One approval covers the work order and the closure plan.
4. Approval creates a planned-closure record, drawn on the map.

Rules:

- The simulation runs in the background and takes 20 to 50 seconds on the full network. Until it finishes, the alert says the impact is being calculated.
- Approval is never blocked. If the operator approves first, the work order goes ahead without a closure plan and the impact arrives as information.
- First version scope: water-leak repairs only **[My call]**. The rule is a small table, so other repair types can be added later.
- A lane closure is new simulation code. The Transportation engine can only close a road section completely. The new project adds a partial closure that reduces the section's capacity in proportion to the lanes closed.

## 7. How it is built

### Base and structure

The new project starts as a copy of `Agentic_AI_City`, without its `.env`, database, backups and legacy pages. The folder is `C:\AI\Agentic_City_View\Riyadh_City_View`.

Mobility code is ported into a new package, `backend/mobility/`:

| Module | Ported from Transportation | Purpose |
|---|---|---|
| `network.py` | `data/osm_network.py`, `data/riyadh_network.py`, `gis/network_source.py` (local part) | Loads the road network from the hosted layers or from files, as you decide below; a 73-segment skeleton for tests |
| `model.py` | `simulation/network_model.py` | Road graph, demand, traffic assignment |
| `engine.py` | `simulation/engine.py`, `road_closure.py`, `traffic_demand.py`, `event_impact.py`, `alternative_routes.py` | Closure, demand and event scenarios |
| `strategies.py` | `simulation/strategies.py` | Five-strategy comparison |
| `access.py` | `simulation/accessibility.py` | Hospital access times |
| `traffic.py` | `services/traffic_simulation.py`, `predictive_analytics.py` | Hourly traffic state, cached |
| `transit.py` | `services/rcrc_service.py` | Metro and bus reference layers |
| `safety.py` | `tools/safety.py`, `tools/infrastructure.py` | Accident history and road-asset condition |
| `jobs.py` | new | One background worker for long simulations, with progress |
| `sources.py` | new | The only place mobility code reads data, so the ported modules do not depend on the Transportation database layer |

Neither source project's database is carried over. The City project stores data in SQLite and the Transportation project in SQLite through SQLAlchemy. The new project uses neither: ArcGIS Online is the system of record (see "ArcGIS Online is the system of record" below).

In the City code, SQLite is used in one file only, `backend/gis/store.py`. Every tool, the crew, approvals and the audit log read and write through that one class. The new project replaces the class and keeps the way the rest of the code calls it.

### Data

| Data | Source | Label shown |
|---|---|---|
| Road network, about 11,000 major-road segments | Built once from the Transportation project's cached OpenStreetMap download | OpenStreetMap, real |
| Traffic volumes and speeds | Modelled by the simulation | Modelled |
| Metro lines and stations, bus routes and stops | RCRC open-data snapshot, copied from Transportation | RCRC open data, credited |
| Eight city-wide hospitals | Transportation reference list | Approximate positions |
| Road incidents, accident history, road-asset condition | Generated, seed-reproducible | Synthetic |
| All city-service data | As in the City project | As in the City project |

New hosted layers: traffic incidents, planned closures, mobility scenario results and emergency facilities. Where the road network, metro and bus layers live is a decision for you, described under "Reference layers" below.

Traffic volumes and speeds are not stored anywhere. The simulation calculates them when they are needed.

### How mobility joins the crew workflow

- A mobility finding is stored as a detection with category `mobility`. Mansour's existing triage turns it into an incident, so alerts, approvals, work orders, dispatch, field verification, closure and learning are all reused.
- The scan cycle gains a mobility watch step. A simulated mobility event wakes only the mobility feed, the same way city-service events wake only their own feed.
- Eight new tools join the tool registry, each with input validation and audit: `traffic_state`, `detect_traffic_incidents`, `simulate_closure`, `compare_closure_strategies`, `simulate_event`, `hospital_access`, `road_safety_context`, `propose_traffic_plan`.
- `propose_traffic_plan` only creates an approval request, like the existing `propose_*` tools.
- `compare_closure_strategies` is not offered to language-model planners because it runs for one to two minutes. The offline planner and the crew can call it.

### ArcGIS Online and Field Maps

This part follows the way the City project connects, which is the only one of the two that has run Field Maps tasks.

**Connection**

- The server signs in with credentials from the new project's own `.env`. Nothing reaches the browser.
- **Sign-in method [Your decision].** The City project uses a username and password, and that is the method proven with Field Maps. The toolkit's authentication guidance prefers an API key with only the needed privileges, or app authentication, over a stored password. I propose to build and prove the connection with the username and password first. In phase 2 I check the Esri documentation, and if an API key can do everything the running server needs, the server switches to it. I have not verified yet that an API key covers creating services, changing layer definitions and editing a web map's task settings, so the setup scripts may still need the account sign-in.

**ArcGIS Online is the system of record**

- All data lives in hosted layers and tables. There is no local database file, and SQLite is removed from the project.
- Every write goes to ArcGIS Online first. The app treats a change as done only when ArcGIS Online confirms it.
- If ArcGIS Online rejects a write or cannot be reached, the action fails and the operator sees the error. Nothing is queued for later.
- An edit made in ArcGIS Online by anyone, in Field Maps or in Map Viewer, is a real change. The app picks it up within 15 seconds.
- The app cannot run without a connection to ArcGIS Online.

**A working copy in memory [Your decision]**

One crew scan reads the layers many times. I have not counted the exact number. There are two ways to serve those reads:

| Option | How it works | Trade-off |
|---|---|---|
| **Working copy in memory (proposed)** | At start-up the app loads the layers from ArcGIS Online into memory and reads from there. Writes still go to ArcGIS Online first. The copy is refreshed every 15 seconds. | Nothing is saved on this computer, and a restart reloads everything from ArcGIS Online. An outside edit can take up to 15 seconds to show. Only one server may run against the layers at a time. |
| No copy | Every read is a request to ArcGIS Online. | Always current. I expect a crew scan to take minutes and not seconds. This is an estimate, not a measurement. |

**What the City project kept only in its local database, and where it goes**

| Was local only | Now |
|---|---|
| Alerts raised by the crew | A hosted table |
| The simulator's answer key, used by the simulated crew and by learning | A hosted table. It is demo scaffolding and is visible in the account. |
| Id counters (`INC-0001`, `WO-0001`, ...) | Worked out at start-up from the highest id in each layer |
| Photos from the in-app Investigator page, saved in a folder | Attachments on the hosted Field Verification layer |
| Conversation focus ("that one") | Stays in memory as today, and is lost on restart |

**Reference layers [Your decision]**

The road network (about 11,000 segments and 7,900 junctions), metro and bus data change rarely. Two options:

| Option | How it works | Trade-off |
|---|---|---|
| **Hosted too (proposed)** | Published once to `CityView` layers and read by the app at start-up | Everything is in ArcGIS Online, which matches your direction. More hosted storage. The Transportation documentation reports about 25 s to build the road model from hosted layers, against about 10 s from a local copy. |
| Files shipped with the app | Read-only data files in the project folder | Faster start-up. These are reference files, not a database, but they are not in ArcGIS Online. |

Two inputs stay as files in both options. They are sources for generating data, not records:

- The OpenStreetMap extract that the demo data and the simulated satellite images are generated from.
- The source files that the reference layers are published from.

**Long text**

The City project defines its long hosted text fields with a 4,000-character limit. With ArcGIS Online as the only store, text that does not fit is a failed write.

- Mobility scenario results store the summary numbers and the recommended strategy. The detailed map preview is recalculated when asked for.
- Alert trails and approval details must fit. In phase 2 I check the documented field-length limit and set the field lengths to suit.

**Demo data and reset**

- First fill: a script generates the synthetic data and loads it into the hosted layers, after a dry run and your yes.
- Reset demo deletes all rows in the `CityView` layers and generates them again in ArcGIS Online. It asks for confirmation. I expect it to take one to two minutes; this is not measured.
- The City project regenerates its data by itself at start-up when the data version changes. That behaviour is removed. The app never deletes data by itself.

**Tests and development without ArcGIS Online [My call]**

A memory-only stand-in with the same interface is used by the tests and for my own checks before the hosted layers exist. It stores nothing and is not for real use.

**Field Maps answers**

Field Maps edits the hosted layers directly, so its answers are already in the system of record. The 15-second refresh brings them into the app, which then assesses them.

**Which account [Your decision]**

The City project uses the account `story_viewer` in the organisation "Esri Saudi Arabia GeoAI Portal". I propose the same account. I do not read or print the password. A small script copies the three ArcGIS lines from a `.env` you name into the new `.env`, without showing them.

**Hosted layers**

One hosted feature service per layer, titled `CityView_<layer name>`:

- Every City layer: assets, water network, sensor readings, detections, changes, extracted features, incidents, work orders, field verification, field workers, facilities, buildings, maintenance history, telemetry, indicators, approvals, audit log, learning settings and simulator events.
- The two the City project kept local: alerts and the simulator's answer key.
- The new mobility layers: traffic incidents, planned closures, emergency facilities, mobility scenario results.
- The reference layers, if you choose to host them.

The layers are private to the account and the group that investigators belong to. Nothing is shared publicly.

Hosted storage uses a small number of ArcGIS credits. I have not estimated the amount.

**Field Maps tasks**

- Approved assignments become tasks on `CityView_Riyadh_Work_Orders`, with the same task fields, text and languages as the City project.
- Three mobility task types are appended to the task-type list: Traffic Incident, Planned Road Closure and Major Event Traffic Plan. Appending keeps the codes of the existing types unchanged.
- The two new Traffic Response investigators are added to the assignee list.
- Investigator logins come from `GEOAI_FIELD_USERS`. Until you give real logins, all investigators map to the one test account, as in the City project.

**The Field Maps map [Your decision]**

The app cannot switch on Tasks by itself. In the City project the web map was made by hand and then edited by scripts. Two ways to get a new map for the `CityView` layers:

| Way | What happens | Trade-off |
|---|---|---|
| **By script (proposed)** | A script reads the working City Investigator Map and its task settings, and creates a **new** web map that points at the `CityView` layers. It also adds the task fields to the new Work Orders layer. | No manual work for you. Unproven: Field Maps may not accept task settings made this way. |
| By hand | You enable Tasks and build the map in Field Maps Designer, following a checklist I write. My scripts then add the Answer button and the bilingual form. | About 15 minutes of your time. This is how the working City map was made. |

If the scripted map shows "Tasks couldn't be loaded" on the phone, we fall back to the manual way.

**How every account change is made**

The same pattern the City project used:

1. Dry run. The script prints what it would create or change and changes nothing.
2. You say yes.
3. A backup of anything being edited is saved in `data/backups/`.
4. The change is applied and read back.

**Protection of the City project's items**

- The app refuses to connect if the layer prefix is `GeoAIOps`.
- The City scripts have the City web-map ids as defaults. In the new project those defaults are removed, so a script changes a web map only when its id is given.
- Scripts create new items and never delete. The City handoff notes that a hosted layer and a web map share one title, so nothing is ever removed by title.

**What I cannot check**

I can check the hosted layers and the server side of the task flow. I cannot use a phone, so the Field Maps app itself needs your test. The City handoff notes that the "verified" alert after Answer, Note and Finish was never confirmed on a phone there either.

### Ask the crew

The offline planner learns the mobility questions in English and Arabic, ported from the Transportation planner:

- Closure impact: "What if King Fahd Road is closed tomorrow from 8 to 4?"
- Best response to a closure.
- Demand growth in an area.
- Event impact at a named place.
- Hospital access.
- Road segments for maintenance priority.
- Traffic now.

Language-model planners get the new tools through the registry automatically.

### Daily brief

`GET /api/brief.pdf?lang=en|ar` builds a one-page city brief from the executive summary and the mobility numbers. It reuses the Transportation PDF and Arabic text-shaping code. The brief is labelled as built from synthetic and modelled data.

### Roles and access

The City roles stay: viewer, investigator (role id `worker` in the code) and operator. The operator approves, as in the City project **[Your decision]**. The Transportation project has a separate approver role; I left it out to keep the City workflow.

The protection mechanism is ported from Transportation:

- One guard on every API route.
- Local mode accepts connections from this computer only.
- Token mode (`API_TOKENS`) for anything reachable from another machine.
- Security response headers, with the content-security policy in report-only mode.

### Languages

Every new label, alert sentence and crew answer gets an English and an Arabic version in the existing translation files. The Arabic is machine-written and needs a native review, the same as in the City project.

## 8. Performance

| Operation | Expected time |
|---|---|
| Loading all layers from ArcGIS Online at start-up | Estimated 10 to 30 s; not measured |
| One write to ArcGIS Online | Estimated a fraction of a second; a crew scan makes tens of writes; not measured |
| Reset demo | Estimated 1 to 2 min; not measured |
| First build of the road model at start-up | About 10 s from files, about 25 s from hosted layers, in the background |
| 24 hourly traffic baselines | 30 to 60 s after start-up, in the background |
| One closure or event scenario | 10 to 25 s |
| Road-impact step (two windows) | 20 to 50 s |
| Five-strategy comparison | 1 to 2 min |

The road-model and simulation figures come from the Transportation project's documentation. The ArcGIS Online figures are my estimates. I have not measured any of them in the new project; phase 2 measures the ArcGIS Online ones.

Every action now waits for ArcGIS Online, so the app will feel slower than the City project, where writes went to a local file first.

Long runs go through the background worker. The crew panel shows Noura as working, and the alert updates when the result arrives. The 60-second crew scan never waits for a simulation.

Tests use the 73-segment skeleton network, so they stay fast.

## 9. Safety rules for this build

- **ArcGIS Online is on, under the prefix `CityView`.** You confirmed the prefix. The app creates and changes only items whose title starts with `CityView`.
- **The City and Transportation hosted items are never changed.** The app refuses the `GeoAIOps` prefix, and no script has a City web-map id as a default.
- **Every account change waits for your yes** after a dry run, as described in section 7.
- **Tests never touch your account.** They run on the memory-only stand-in. The live app writes only to `CityView` layers.
- **The app never deletes data by itself.** Rows are removed only by Reset demo, which asks first.
- **The two source projects are read-only.** I copy from them and never write to them. The one exception is reading the City Investigator Map from ArcGIS Online as a template, which changes nothing.
- **Own port.** Port 8020, so it does not collide with a City or Transportation server on port 8000 **[My call]**.

## 10. Build order and your checkpoints

| Phase | Result | You review |
|---|---|---|
| 0. Toolkit setup | Esri documentation server connected, or the fallback agreed (section 13) | You connect the server, or tell me to use the fallback |
| 1. Scaffold | Copy of City under the new name and port. SQLite removed; the memory-only stand-in in its place. City tests passing | |
| 2. ArcGIS Online as the record | Sign-in check, `CityView` hosted layers created and filled, the app reading and writing ArcGIS Online, timings measured | **Checkpoint 1:** you approve each dry run, then see the City use cases running on ArcGIS Online |
| 3. Mobility engine | Road network, simulation and strategies ported, with tests | |
| 4. Map layers | Traffic, metro, bus, hospitals on both maps; reference layers published if you chose that | **Checkpoint 2:** you approve the dry run, then see the new layers |
| 5. Crew and events | Nasser, Noura, Fahad; three mobility events; alerts and approvals; the mobility hosted layers | You approve the dry run for the new layers |
| 6. Cross-domain link | Road-impact line on water-leak repairs | **Checkpoint 3:** the headline story end to end |
| 7. Field Maps | Task fields, new web map, Answer button, bilingual form, mobility task types | **Checkpoint 4:** you approve each dry run, then test on a phone |
| 8. Interface | Lifecycle strip, strategy table, feed cards, Executive Hub numbers | |
| 9. Ask the crew | Mobility questions in English and Arabic | |
| 10. Brief and access | Daily brief PDF; roles and protection | |
| 11. Finish | Arabic pass, documentation, demo script, full check in the browser | **Checkpoint 5:** final review |

ArcGIS Online now comes second, because the app cannot run for real without it. The mobility layers are added to the account later, in phases 4 and 5, each after its own dry run.

## 11. Testing

- The City test suite is carried over and adjusted. It has 156 tests and takes about six minutes.
- New tests cover the mobility engine, the three mobility events, the cross-domain link, the new API routes, the new roles guard and the Arabic planner questions.
- All tests run without ArcGIS Online, on the memory-only stand-in and the skeleton network. The ArcGIS Online store and the Field Maps task flow are tested against a stand-in for the hosted layers.
- The live ArcGIS Online connection is checked by hand. At checkpoint 1: layer counts read back, one write confirmed, one failed write shown as an error, and a restart that reloads the same data. At checkpoint 4: one task taken from approval to a verified alert.
- Each checkpoint includes a check in the browser, in English and in Arabic.

## 12. Smaller calls I made

| Call | Reason |
|---|---|
| The new folder is a local git repository; nothing is pushed anywhere | Lets each phase be reviewed and undone |
| Environment variable names keep the `GEOAI_` prefix | The City scripts and documentation carry over unchanged |
| New Python packages: `networkx`, `reportlab`, `arabic-reshaper`, `python-bidi` | Needed by the simulation and the PDF brief |
| Vanilla JavaScript, no build step | Same as both source projects |
| ArcGIS Maps SDK for JavaScript stays at 4.30 in the first version | Both source apps run on it. The toolkit says to keep compatible existing dependencies, and to use the latest version for new projects. I have not checked what moving to the current version would need; that check is in phase 4 (section 13) |
| The City project's own look is kept; Calcite Design System is not adopted | Calcite would change how every page looks, which is a major change you have not asked for |
| Hospital access uses the eight city-wide hospitals, not the City project's district facilities | The simulation needs city-wide destinations |
| Bus stops (3,010 points) load only when the Bus layer is switched on | Keeps the map fast |
| The in-app Investigator page is on by default | You chose to keep it next to Field Maps |
| Only one server runs against the `CityView` layers at a time | The working copy and the id counters assume a single writer |
| The `GEOAI_OFFLINE` and `GEOAI_DB_PATH` settings are removed | There is no local database to point at |
| New Python packages for ArcGIS: `arcgis` and `six` | The City handoff notes that without `six` the hosted layers look missing |
| Citizen reports stay off and there is no weather feed | Your earlier decisions in the City project |
| Traffic incidents, closure requests and event notices come from the Simulate an event menu | No live feed is connected, the same as in both source projects |

## 13. ArcGIS agentic developer toolkit

### What I took this to mean

I could not find an Esri product with the exact name "ArcGIS agentic developer toolkit". I matched it to what is installed on this computer and published by Esri as `Esri/esri-developer-agent-skills`:

- **Esri agent skills.** Fifteen are installed here, including the ones this project needs.
- **Esri's documentation server for developers** (an MCP server), which lets me look up current Esri documentation while I work.

I also took it to mean a toolkit for **how the project is built**, not a new feature inside the app. **[Your decision]** If you meant something else, for example the crew's tools offered to other AI agents through an MCP server, tell me and I will add it.

### What it changes in this project

| Toolkit part | Used for | When |
|---|---|---|
| `gather-arcgis-application-requirements` | The requirements summary below | Done in this revision |
| `follow-arcgis-authentication-patterns` | The server's sign-in method and credential handling | Phase 2, and the sign-in decision in section 7 |
| `build-with-arcgis-maps-sdk-for-javascript` | Map layers, hour slider, 2D and 3D, the version check for 4.30 | Phases 4 and 8 |
| `build-with-arcgis-api-for-python` | Hosted layers, the ArcGIS Online store, the Field Maps map and task scripts | Phases 2, 4, 5 and 7 |
| Esri documentation server | Checking every ArcGIS-specific choice against current documentation before I build on it | Phases 2, 4 and 7 |

Not used: `build-with-calcite-design-system` (see section 12), `build-with-arcgis-rest-js` and the mobile, game-engine and open-source map skills. The project has no use for them.

### One setup step needs you

The documentation server is **not connected** in this session. The installed skills name its address as `https://developers-mcp.arcgis.com/mcp`. A web search also showed a community copy that uses a different address, and I could not confirm which is current.

- **Proposed:** you add the server in your Claude settings, using the address from Esri's own repository. I do not change your Claude configuration myself.
- **Fallback:** I read the official Esri documentation on the web and say so each time.

### Rules the toolkit adds

- Every ArcGIS-specific choice is checked against Esri documentation before it is built on. Where I could not check, I say so.
- Secrets are never asked for in chat and never shown from files.
- A protected item is never made public to get around an access problem.
- The sibling projects in this workspace are not changed.

### ArcGIS requirements handoff summary

- **Work Target:** New application, built from a copy of an existing one (`Agentic_AI_City`), with features ported from a second (`Agentic_AI_Transportation`).
- **Project Folder:** `Riyadh_City_View` inside `C:\AI\Agentic_City_View`.
- **ArcGIS Product Context:** ArcGIS Online.
- **Target Platform:** Web (desktop browser) for the command center; ArcGIS Field Maps on phones for investigators.
- **Delivery Scope:** Demo-grade prototype. Required now: the seven use cases, hosted layers, Field Maps tasks. Deferred: browser sign-in with ArcGIS, production hardening.
- **Identity & Access Model:** The web app's users do not sign in to ArcGIS; app roles guard the API. The server holds one ArcGIS credential and acts as the owner account. Investigators sign in to Field Maps with their own ArcGIS Online accounts.
- **Core Features and Operations:** 2D maps and 3D scenes; data hosting (hosted feature layers as the system of record, created and edited by the server, with no local database); portal content management (a web map and its task settings); data visualization; field data collection with Field Maps tasks.

#### Remaining assumptions

1. Demo-grade prototype, not production. This follows from the audience guess you accepted; you have not said it yourself.
2. The ArcGIS Online account is the one the City project uses.
3. The owner account can create hosted feature layers and web maps. The sign-in check in phase 2 confirms this before anything is created.
4. ArcGIS Maps SDK for JavaScript 4.30 is still served from Esri's CDN and still works with the City code. Not checked yet.
5. "No local database" allows a working copy in memory that is never saved to disk. This is a decision waiting for you in section 7.
6. ArcGIS Online is fast enough for the crew's 60-second scan when reads come from the working copy. Measured in phase 2.

#### Next agent actions

- [ ] Route to `follow-arcgis-authentication-patterns` in phase 2 for the server's sign-in method.
- [ ] Route to `build-with-arcgis-api-for-python` in phases 2, 4, 5 and 7 for hosted layers, the ArcGIS Online store and Field Maps.
- [ ] Route to `build-with-arcgis-maps-sdk-for-javascript` in phase 4 for the map layers and the version check.

## 14. What is left to the builder

- Exact field lists of the four new layers.
- Wording of alert titles and trail sentences.
- Colours for the three new agents.
- Thresholds for "abnormal congestion".
- The layout details of the strategy table and the lifecycle strip.
