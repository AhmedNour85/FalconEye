"""Entry point:  python -m backend.main   (or: uvicorn backend.api.app:app_factory --factory --port 8020)

On this computer it listens on 127.0.0.1:8020, as before. On a hosting service set HOST=0.0.0.0 and the host's PORT; set
FORWARDED_ALLOW_IPS to the host's proxy (or "*" when only the proxy can reach the app) so visitors' real addresses are seen.
"""
import logging
import os

import uvicorn

PORT = 8020          # 8000 is left free for the Agentic_AI_City and Agentic_AI_Transportation servers

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and not (os.environ.get("API_TOKENS") or os.environ.get("GEOAI_API_TOKENS")):
        logging.getLogger("geoai").warning("HOST=%s but API_TOKENS is empty: every visitor from another computer will be refused.", host)
    uvicorn.run("backend.api.app:app_factory", factory=True, host=host, port=int(os.environ.get("PORT", PORT)), reload=False,
                proxy_headers=True, forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))
