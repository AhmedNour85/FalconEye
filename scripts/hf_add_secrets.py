"""Copy the Falcon Eye settings from .env into a Hugging Face Space's secrets, so they don't have to be typed by hand.

Run it yourself:   .venv\\Scripts\\python.exe scripts\\hf_add_secrets.py ahmednour/falcon-eye
It asks for a Hugging Face access token with write access (huggingface.co/settings/tokens). The token is not stored.
Values are sent only to huggingface.co and are never printed.
"""
import getpass
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

KEYS = ["ARCGIS_URL", "ARCGIS_USERNAME", "ARCGIS_PASSWORD", "ARCGIS_LAYER_PREFIX", "ARCGIS_JS_API_KEY", "API_TOKENS", "GEOAI_FIELD_USERS"]


def main() -> int:
    space = sys.argv[1] if len(sys.argv) > 1 else "ahmednour/falcon-eye"
    env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    values = {k: (env.get(k) or "").strip() for k in KEYS}
    values["PUBLIC_ORIGINS"] = "https://" + space.replace("/", "-").replace("_", "-").lower() + ".hf.space"
    missing = [k for k, v in values.items() if not v and k not in ("ARCGIS_JS_API_KEY", "GEOAI_FIELD_USERS")]
    if missing:
        print("These are empty in .env:", ", ".join(missing))
        return 1
    token = getpass.getpass(f"Hugging Face token with write access (typing is hidden), for {space}: ").strip()
    if not token:
        print("No token given. Nothing was sent.")
        return 1
    url = f"https://huggingface.co/api/spaces/{space}/secrets"
    ok = True
    for k, v in values.items():
        if not v:
            print(f"  skipped {k} (empty in .env)")
            continue
        r = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json={"key": k, "value": v}, timeout=30)
        print(f"  {k}: {'saved' if r.is_success else f'failed ({r.status_code})'}")
        ok = ok and r.is_success
        if r.status_code in (401, 403):
            print("The token was refused. Make a token with 'Write' access and try again.")
            return 1
    print("Done. Now choose 'Restart this Space' in the Space's Settings." if ok else "Some settings failed; see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
