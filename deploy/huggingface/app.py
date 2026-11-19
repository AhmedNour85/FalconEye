"""Falcon Eye on a free Hugging Face Space (Gradio SDK, which runs this file).

On each start it fetches the latest code from GitHub and runs the Falcon Eye server on the Space's port (7860), in place of a Gradio app.
So a push to GitHub is picked up by the next restart. Secrets (ArcGIS sign-in, access codes) come from the Space's
Settings -> Variables and secrets, which the Space passes in as environment variables.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = os.environ.get("FALCON_REPO", "https://github.com/AhmedNour85/FalconEye.git")
BRANCH = os.environ.get("FALCON_BRANCH", "main")
CODE = Path(os.environ.get("FALCON_DIR") or Path(tempfile.gettempdir()) / "falcon-eye")


def fetch() -> None:
    if CODE.exists():
        shutil.rmtree(CODE)
    print(f"Fetching {REPO} ({BRANCH}) ...", flush=True)
    subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, str(CODE)], check=True)
    # the Space installed requirements.txt when it was built; this only adds anything the code needs since then (a few seconds otherwise)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", str(CODE / "requirements.txt")], check=False)


def main() -> None:
    fetch()
    env = {"HOST": "0.0.0.0", "PORT": "7860", "FORWARDED_ALLOW_IPS": "*",
           "GEOAI_STORE": "arcgis", "GEOAI_FIELD_FORM": "1", "GEOAI_FIELD_LANG": "both"}
    for k, v in env.items():
        os.environ.setdefault(k, v)          # a Space variable with the same name wins
    os.environ["PORT"] = "7860"               # the Space only serves this port
    os.chdir(CODE)
    os.execv(sys.executable, [sys.executable, "-m", "backend.main"])


if __name__ == "__main__":
    main()
