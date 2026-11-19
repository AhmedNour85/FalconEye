# Publish Falcon Eye as a public demo (ArcGIS Online)

The public copy runs the default configuration: the existing `CityView_*` hosted layers in ArcGIS Online are the system of record. Nothing is created or reset. GitHub keeps the code; a hosting service runs it.

## Before you start

- **One server at a time.** The app keeps a lock in ArcGIS Online and renews it about every 60 s. A second server refuses to start until the lock is 150 s old. Stop the server on your PC before the public copy starts. From then on the public copy is the server, also for Field Maps.
- **Approvals change real records.** Visitors sign in with an access code, and the code's role decides what they can do:
  - `viewer` can look.
  - `worker` can also send field reports.
  - `operator` can also approve, reject and reset.
- **Keep secrets out of git.** `.env` is in `.gitignore`. Your ArcGIS sign-in goes into the host's secret settings only. Consider a separate ArcGIS account for the demo, with access to the `CityView_*` layers only.

## 1. Make access codes

Run this once for each code you need:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Then join them as `API_TOKENS=<code-1>=operator,<code-2>=viewer`. Give the operator code only to people who may approve.

## 2. Put the code on GitHub

```bash
git add -A
```

```bash
git status
```

Check the list before you commit. It must not include `.env`, `.venv/` or `qa-reports/`.

```bash
git commit -m "Public demo: sign-in, hosting settings, security fixes"
```

Create an empty repository on GitHub, without a README. Then:

```bash
git remote add origin https://github.com/<you>/<repo>.git
```

```bash
git push -u origin main
```

## 3. Free: run it on a Hugging Face Space

A free Space has 2 CPUs and 16 GB of memory. It sleeps after 48 hours without visitors; the first visit after that waits 2 to 3 minutes while it starts and loads the layers. The Space holds two files only, from `deploy/huggingface/`; its build fetches the code from GitHub.

1. Create a free account on huggingface.co.
2. Choose **New Space**. Name it, for example `falcon-eye`. Choose **Docker**, then **Blank**, hardware **CPU basic (free)**, and **Public** (a private Space asks every visitor to sign in to Hugging Face). Choose **Create Space**.
3. In the Space's **Settings → Variables and secrets**, choose **New secret** for each of these, with the same values as in your `.env`:
   `ARCGIS_URL`, `ARCGIS_USERNAME`, `ARCGIS_PASSWORD`, `ARCGIS_LAYER_PREFIX`, `ARCGIS_JS_API_KEY`, `API_TOKENS`, `GEOAI_FIELD_USERS`.
   Add one more, `PUBLIC_ORIGINS`, set to the Space's direct address: `https://<your-hf-name>-<space-name>.hf.space`, all in lowercase (for example `https://ahmednour85-falcon-eye.hf.space`).
4. **Stop the server on your PC** and wait about 3 minutes, so its lock in ArcGIS Online runs out.
5. In the Space's **Files** tab, choose **Add file → Create a new file**. Name it `Dockerfile` and paste the content of `deploy/huggingface/Dockerfile`. Commit it. Then open `README.md` in the Space, choose **Edit**, replace everything with the content of `deploy/huggingface/README.md`, and commit. The build starts by itself; follow it under **Logs**. The first build takes about 10 minutes.
6. When the Space shows **Running**, open the direct address (`https://….hf.space`), not the Space page on huggingface.co: the app refuses to be shown inside another site, so the Space page stays blank.

**Updating:** push to GitHub, then choose **Settings → Factory rebuild**. The build fetches the new code. If the new copy says the lock is held, wait 3 minutes and choose **Factory rebuild** again.

## 4. Paid: create the service on Render

1. In Render, choose **New → Blueprint** and pick the repository. Render reads `render.yaml`: a Python web service on an always-on plan, started with `python -m backend.main`, with the health check on `/api/health`.
2. Render asks for each secret:

   | Setting | Value |
   |---|---|
   | `ARCGIS_URL`, `ARCGIS_USERNAME`, `ARCGIS_PASSWORD`, `ARCGIS_LAYER_PREFIX`, `ARCGIS_JS_API_KEY` | The same values as in your `.env` |
   | `API_TOKENS` | Your access codes from step 1 |
   | `PUBLIC_ORIGINS` | The service's address, for example `https://falcon-eye.onrender.com`. You can set it after the first deploy, once you know the address. |

3. **Stop the server on your PC.** Then apply the blueprint. The first start loads every layer from ArcGIS Online, which takes a minute or two.
4. Open the address. You land on **Sign in**. Enter a code, and you are taken to the page you asked for. Sign out with `/signout`.

## Redeploying

Render starts the new copy before it stops the old one. The new copy then finds the lock held and refuses to start. The old copy keeps running, so nothing breaks, but the update doesn't take effect. To redeploy:

1. In Render, choose **Suspend** for the service, then wait about 3 minutes. The old copy hands the lock back when it stops cleanly, and the 150 s timeout covers the rest.
2. Choose **Resume**, then **Manual Deploy**.

To avoid this, attach a small persistent disk to the service. Render then stops the old copy before it starts the new one, at the cost of a short break on each deploy.

## Checks after the first deploy

- `/api/health` returns `"status": "ok"` and the ArcGIS Online counts.
- A viewer code can open every page, but **Approve** answers "role 'viewer' cannot perform this action".
- An operator code can approve. The change appears in ArcGIS Online.

## Other hosts

Any host that runs Python works. Set these:

- **Start command:** `python -m backend.main`
- **Settings:** `HOST=0.0.0.0` and `FORWARDED_ALLOW_IPS=*`. Most hosts set `PORT` themselves.
- **Secrets:** the same as in the table above.
- **Memory:** at least 1 GB. The server uses about 310 MB at rest and more during traffic simulations.
