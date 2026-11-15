"""Entry point:  python -m backend.main   (or: uvicorn backend.api.app:app_factory --factory --port 8000)"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.api.app:app_factory", factory=True, host="127.0.0.1", port=8000, reload=False)
