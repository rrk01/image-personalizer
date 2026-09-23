import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ROOT, Settings
from app.db import Database
from app.services.generation import Generator


class StartRequest(BaseModel):
    preferences: str = Field(min_length=1, max_length=1000)
    mutation: int = Field(default=20, ge=0, le=100, strict=True)


class RatingRequest(BaseModel):
    score: int = Field(ge=0, le=100, strict=True)
    mutation: int = Field(ge=0, le=100, strict=True)


def create_app(settings=None):
    settings = settings or Settings()
    db = Database(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app):
        db.recover()
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            app.state.generator = Generator(db, settings, client)
            yield
            task = app.state.generator.task
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Image Personalizer", lifespan=lifespan)
    app.state.db = db
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # Keep another website from spending local GPU work through the browser.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Use the app's local page for this request."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def public(row):
        if row is None:
            return None
        return {k: v for k, v in row.items() if k not in {"workflow_json", "llm_request_json"}} | {
            "image_url": f"/api/images/{row['id']}" if row["image_name"] else None,
        }

    def idle():
        if app.state.generator.busy:
            raise HTTPException(409, "A generation is already running.")

    def current(generation_id):
        session = db.session()
        row = db.get(generation_id)
        if not session or not row or row["session_id"] != session["id"]:
            raise HTTPException(404, "This generation is not in the current session.")
        return session, row

    @app.get("/api/state")
    async def state():
        session = db.session()
        rows = db.generations(session["id"]) if session else []
        return {"session": session, "generation": public(rows[-1]) if rows else None,
                "rated_count": sum(r["score"] is not None for r in rows), "busy": app.state.generator.busy}

    @app.get("/api/health")
    async def health():
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            async def check(url, ollama=False):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    if ollama and settings.ollama_model not in {m["name"] for m in response.json().get("models", [])}:
                        return "Model missing"
                    return "Ready"
                except (httpx.HTTPError, ValueError, KeyError):
                    return "Offline"
            ollama, comfy = await asyncio.gather(check(settings.ollama_url + "/api/tags", True), check(settings.comfyui_url + "/system_stats"))
            return {"ollama": ollama, "comfyui": comfy}

    @app.post("/api/generate", status_code=202)
    async def generate(payload: StartRequest):
        idle()
        preferences = payload.preferences.strip()
        if not preferences:
            raise HTTPException(422, "Enter a few starting preferences.")
        session = db.session()
        if session and db.generations(session["id"]):
            raise HTTPException(409, "Rate the current image, retry, or start over.")
        session = session or db.create_session(preferences, payload.mutation)
        return public(app.state.generator.create(session, payload.mutation))

    @app.post("/api/generations/{generation_id}/rate", status_code=202)
    async def rate(generation_id: str, payload: RatingRequest):
        session, row = current(generation_id)
        rows = db.generations(session["id"])
        if row["score"] is not None:
            # A double click or lost response must not save another rating/job.
            return public(next(r for r in rows if r["sequence"] == row["sequence"] + 1))
        idle()
        if row["status"] != "complete" or rows[-1]["id"] != generation_id:
            raise HTTPException(409, "Wait for the current image before rating it.")
        return public(app.state.generator.create(session, payload.mutation, rating=(generation_id, payload.score)))

    @app.post("/api/generations/{generation_id}/retry", status_code=202)
    async def retry(generation_id: str):
        idle()
        session, row = current(generation_id)
        if row["status"] != "error" or db.generations(session["id"])[-1]["id"] != generation_id:
            raise HTTPException(409, "Only the latest failed generation can be retried.")
        app.state.generator.start(generation_id)
        return public(db.get(generation_id))

    @app.post("/api/reset")
    async def reset():
        idle()
        db.reset()
        return {"ok": True}

    @app.get("/api/images/{generation_id}")
    async def image(generation_id: str):
        row = db.get(generation_id)
        if not row or not row["image_name"]:
            raise HTTPException(404, "Image not found.")
        path = settings.data_dir / "images" / row["image_name"]
        if not path.is_file():
            raise HTTPException(404, "The saved image file is missing.")
        return FileResponse(path, media_type="image/png")

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "web/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app


app = create_app()
