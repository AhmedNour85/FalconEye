# Run Falcon Eye on a Mac

Two ways to run it:

- **Memory mode.** No ArcGIS account is needed. The app makes up demo data at start-up and keeps nothing when it stops. Use this to try the demo or to present it offline (the base map still needs internet).
- **ArcGIS Online mode.** The real setup. The records live in the `CityView_*` hosted layers. Only one server at a time may work on those layers, so stop the Windows server first.

Commands are for Terminal (zsh), run from the project folder.

## 1. Install Python 3.10 to 3.13

Check what you have:

```bash
python3 --version
```

If it is missing or older than 3.10, install it from python.org or with Homebrew:

```bash
brew install python@3.12
```

## 2. Copy the project to the Mac

Copy the whole `Riyadh_City_View` folder, including `data/`. Leave out these:

- `.venv`: it is built for Windows and does not work on a Mac.
- `.env`: it holds your sign-in. Move it only by a private route, never through a shared folder or chat.

## 3. Create the environment

```bash
cd ~/path/to/Riyadh_City_View
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install --upgrade pip
```

```bash
.venv/bin/python -m pip install -r requirements.txt
```

The `arcgis` package is large, so the install takes a few minutes.

## 4a. Run in memory mode (no account)

```bash
GEOAI_STORE=memory .venv/bin/python -m backend.main
```

Open http://127.0.0.1:8020. Press Ctrl+C in Terminal to stop.

## 4b. Run on ArcGIS Online

1. Create `.env` from your existing sign-in file. The script copies only the three ArcGIS sign-in lines and never prints them.

   ```bash
   .venv/bin/python scripts/make_env.py /path/to/your/other/.env
   ```

   Or copy `.env.example` to `.env` and fill in `ARCGIS_URL`, `ARCGIS_USERNAME` and `ARCGIS_PASSWORD` by hand.

2. Check the account. This only reads.

   ```bash
   .venv/bin/python scripts/setup_arcgis.py
   ```

3. **Stop the Windows server.** A second server on the same layers refuses to start.

4. Start the server:

   ```bash
   .venv/bin/python -m backend.main
   ```

5. Open http://127.0.0.1:8020.

The layers already exist, so do not run `create_feature_layers.py`, `initialize_demo.py` or `publish_reference_layers.py` again. Each of them is a dry run unless you add `--apply`. `initialize_demo.py --apply` deletes the demo rows.

## 5. Optional settings in `.env`

| Setting | What it does |
|---|---|
| `ANTHROPIC_API_KEY` and `GEOAI_PLANNER=claude` | The crew uses the Claude planner instead of the offline rule planner. |
| `ARCGIS_JS_API_KEY` | Esri base maps in the browser. |
| `API_TOKENS` | Token mode: every call needs a token. Without it, only this Mac can use the app (local mode). |
| `PDF_ARABIC_FONT` | Only needed if the Arabic daily brief says no Arabic font was found. The app normally uses `/System/Library/Fonts/Supplemental/Arial.ttf`. |

## 6. Check that it works (optional)

The tests run in memory mode and never contact ArcGIS Online. The full run takes about 15 minutes.

```bash
GEOAI_STORE=memory .venv/bin/python -m pytest -q
```

## Troubleshooting

| What you see | What to do |
|---|---|
| `address already in use` on 8020 | Another server is running. Find it with `lsof -i :8020`, then stop it, or press Ctrl+C in its Terminal window. |
| `zsh: command not found: python` | On a Mac use `python3`, or `.venv/bin/python` once the environment exists. |
| The server says another server is working on the layers | The Windows server is still running. Stop it first. |
| The map stays grey | The ArcGIS map needs internet access. |
| The pip install fails on `arcgis` | Use Python 3.10 to 3.13. Newer versions may not have the package yet. |
| Other computers cannot open the page | That is on purpose: the server listens only on this Mac (127.0.0.1). |
