# Falcon Eye on a free Hugging Face Space (Docker). The Space holds only this file and README.md:
# the build fetches the code from GitHub, so every push to GitHub is picked up by the next restart.
# Secrets (ArcGIS sign-in, access codes) go in the Space's Settings -> Variables and secrets, never here.
FROM python:3.10-slim

# git fetches the code; DejaVu Sans has Arabic letters for the daily brief PDF
RUN apt-get update && apt-get install -y --no-install-recommends git fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user

ARG REPO=https://github.com/AhmedNour85/FalconEye.git
ARG BRANCH=main
# this file changes whenever the branch gets a new commit, so the code below is fetched again instead of taken from the build cache
ADD --chown=user https://api.github.com/repos/AhmedNour85/FalconEye/git/refs/heads/${BRANCH} /tmp/version.json
RUN git clone --depth 1 --branch ${BRANCH} ${REPO} app
WORKDIR /home/user/app
RUN pip install --no-cache-dir --user -r requirements.txt

# a Space serves port 7860 behind its own proxy
ENV HOST=0.0.0.0 PORT=7860 FORWARDED_ALLOW_IPS=* GEOAI_STORE=arcgis GEOAI_FIELD_FORM=1 GEOAI_FIELD_LANG=both
EXPOSE 7860
CMD ["python", "-m", "backend.main"]
