"""Entry point:  python -m backend.main   (or: uvicorn backend.api.app:app_factory --factory --port 8020)"""
import uvicorn

PORT = 8020          # 8000 is left free for the Agentic_AI_City and Agentic_AI_Transportation servers

if __name__ == "__main__":
    uvicorn.run("backend.api.app:app_factory", factory=True, host="127.0.0.1", port=PORT, reload=False)
