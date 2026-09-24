import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ROOT, Settings
from app.aspect_ratios import ASPECT_RATIOS, AspectRatio, image_format
from app.db import Database
from app.services.generation import Generator
from app.statistics import score_statistics


class StartRequest(BaseModel):
    aspect_ratio: AspectRatio = "1:1"
    name: str = Field(default="", max_length=80)
    preferences: str = Field(min_length=1, max_length=1000)
    mutation: int = Field(default=20, ge=0, le=100, strict=True)


class RatingRequest(BaseModel):
    aspect_ratio: AspectRatio | None = None
    score: int = Field(ge=0, le=100, strict=True)
    mutation: int = Field(ge=0, le=100, strict=True)
    feedback: str = Field(default="", max_length=1000)
    generate_next: bool = Field(default=True, strict=True)


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def create_app(settings=None):
    settings = settings or Settings()
    db = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal db
        db = Database(settings.data_dir)
        app.state.db = db
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
            "image_format": image_format(row["aspect_ratio"]),
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
        statistics = score_statistics(rows)
        return {"session": session, "generation": public(rows[-1]) if rows else None,
                "aspect_ratios": [image_format(ratio) for ratio in ASPECT_RATIOS],
                "rated_count": statistics["count"], "statistics": statistics, "busy": app.state.generator.busy}

    @app.get("/api/sessions")
    async def sessions():
        return db.sessions()

    @app.post("/api/sessions/{session_id}/load")
    async def load_session(session_id: str):
        idle()
        if not db.load_session(session_id):
            raise HTTPException(404, "Session not found.")
        return await state()

    @app.post("/api/sessions/{session_id}/rename")
    async def rename_session(session_id: str, payload: NameRequest):
        idle()
        name = payload.name.strip()
        if not name:
            raise HTTPException(422, "Enter a session name.")
        if not db.rename_session(session_id, name):
            raise HTTPException(404, "Session not found.")
        return {"ok": True}

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
        session = session or db.create_session(preferences, payload.mutation, payload.name, payload.aspect_ratio)
        return public(app.state.generator.create(session, payload.mutation, aspect_ratio=payload.aspect_ratio))

    @app.post("/api/generations/{generation_id}/rate", status_code=202)
    async def rate(generation_id: str, payload: RatingRequest):
        session, row = current(generation_id)
        rows = db.generations(session["id"])
        successor = next((r for r in rows if r["sequence"] == row["sequence"] + 1), None)
        if payload.generate_next and row["score"] is not None and successor:
            # A double click or lost response must not save another rating/job.
            return public(successor)
        idle()
        if row["status"] != "complete" or rows[-1]["id"] != generation_id:
            raise HTTPException(409, "Wait for the current image before rating it.")
        feedback = payload.feedback.strip()
        if not payload.generate_next:
            db.save_rating(generation_id, payload.score, feedback, payload.mutation, payload.aspect_ratio)
            return JSONResponse(public(db.get(generation_id)), status_code=200)
        return public(app.state.generator.create(session, payload.mutation,
            rating=(generation_id, payload.score), feedback=feedback, aspect_ratio=payload.aspect_ratio))

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
