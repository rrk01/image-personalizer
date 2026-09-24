import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.db import Database
from app.main import create_app
from app.preferences import is_mutation, select_examples
from app.services.generation import Generator
from app.services.ollama import Ollama


@pytest.fixture
def client(tmp_path, monkeypatch):
    async def complete(self, generation_id):
        self.db.update(generation_id, status="complete", prompt="A floral woodblock print.", rationale="First interpretation.", image_name=f"{generation_id}.png")

    monkeypatch.setattr(Generator, "run", complete)
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        yield client


def test_score_zero_and_duplicate_rating_create_only_one_next_image(client):
    first = client.post("/api/generate", json={"preferences": "Japanese, floral", "mutation": 0}).json()
    assert first["mutated"] == 0
    response = client.post(f"/api/generations/{first['id']}/rate", json={"score": 0, "mutation": 100})
    assert response.status_code == 202
    second = response.json()
    assert second["mutated"] == 1
    duplicate = client.post(f"/api/generations/{first['id']}/rate", json={"score": 99, "mutation": 0})
    assert duplicate.json()["id"] == second["id"]
    state = client.get("/api/state").json()
    assert state["rated_count"] == 1
    assert state["generation"]["sequence"] == 2
    assert client.app.state.db.get(first["id"])["score"] == 0


@pytest.mark.parametrize("score", [-1, 101, 2.5, "80"])
def test_invalid_ratings_do_not_create_jobs(client, score):
    row = client.post("/api/generate", json={"preferences": "Flowers", "mutation": 20}).json()
    assert client.post(f"/api/generations/{row['id']}/rate", json={"score": score, "mutation": 20}).status_code == 422
    assert client.get("/api/state").json()["rated_count"] == 0


def test_reset_preserves_old_data_and_isolates_new_preferences(client):
    old = client.post("/api/generate", json={"preferences": "Flowers", "mutation": 20}).json()
    assert client.post("/api/reset").status_code == 200
    assert client.get("/api/state").json()["session"] is None
    assert client.app.state.db.get(old["id"])["prompt"]
    client.post("/api/generate", json={"preferences": "Architecture", "mutation": 20})
    assert client.post(f"/api/generations/{old['id']}/rate", json={"score": 80, "mutation": 20}).status_code == 404
    assert client.get("/api/state").json()["rated_count"] == 0


def test_busy_guards_and_cross_origin_requests(tmp_path, monkeypatch):
    async def pending(self, generation_id):
        await asyncio.Event().wait()

    monkeypatch.setattr(Generator, "run", pending)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        payload = {"preferences": "Flowers", "mutation": 20}
        assert c.post("/api/generate", json=payload, headers={"Origin": "https://other.example"}).status_code == 403
        first = c.post("/api/generate", json=payload).json()
        sid = c.get("/api/state").json()["session"]["id"]
        assert c.post(f"/api/sessions/{sid}/load").status_code == 409
        assert c.post(f"/api/sessions/{sid}/rename", json={"name": "New name"}).status_code == 409
        assert c.post("/api/generate", json=payload).status_code == 409
        assert c.post("/api/reset").status_code == 409
        assert c.post(f"/api/generations/{first['id']}/rate", json={"score": 50, "mutation": 20}).status_code == 409


def test_restart_preserves_rating_and_recovers_interrupted_job(tmp_path):
    db = Database(tmp_path)
    session = db.create_session("Flowers", 20)
    first = db.create_generation(session["id"], 20, False, 42, {})
    db.update(first["id"], status="complete", image_name="image.png")
    second = db.create_generation(session["id"], 20, False, 43, {}, (first["id"], 100))
    db.update(second["id"], status="generating", comfy_prompt_id="persisted-job")
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        state = c.get("/api/state").json()
        assert state["rated_count"] == 1
        assert state["generation"]["status"] == "error"
        assert state["generation"]["comfy_prompt_id"] == "persisted-job"
        assert c.app.state.db.get(first["id"])["score"] == 100


def test_bounded_examples_include_high_low_recent_and_zero():
    rows = [{"id": str(i), "sequence": i, "score": i, "prompt": f"Prompt {i}"} for i in range(101)]
    examples = select_examples(rows)
    assert len(examples) <= 10
    assert {0, 100, 99}.issubset({r["score"] for r in examples})
    assert is_mutation(0) is False
    assert is_mutation(100) is True


def test_complete_service_loop_unloads_before_submission_and_recovers_without_resubmit(tmp_path):
    calls = []
    job_id = None
    png = b"\x89PNG\r\n\x1a\nexample"

    def handler(request):
        nonlocal job_id
        path = request.url.path
        calls.append(path)
        if path == "/queue":
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        if path == "/system_stats":
            return httpx.Response(200, json={"devices": [{"torch_vram_total": 0}]})
        if path == "/free":
            return httpx.Response(200)
        if path == "/api/chat":
            body = json.loads(request.content)
            assert body["keep_alive"] == 0
            assert body["options"]["num_predict"] == 512
            context = json.loads(body["messages"][1]["content"])
            assert context["scored_examples"][0]["feedback"] == "Keep the blue flowers."
            assert context["score_statistics"]["mean"] == 70
            assert context["image_format"]["aspect_ratio"] == "9:16"
            return httpx.Response(200, json={"done_reason": "stop", "message": {"content": json.dumps({"prompt": "Cherry blossoms in a Japanese garden.", "rationale": "Explore a garden composition."})}})
        if path == "/api/generate":
            assert json.loads(request.content)["keep_alive"] == 0
            return httpx.Response(200, json={"done": True})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        if path == "/prompt":
            body = json.loads(request.content)
            job_id = body["prompt_id"]
            assert body["prompt"]["452"]["inputs"]["prompt"].startswith("Cherry")
            assert body["prompt"]["458"]["inputs"]["steps"] == 25
            assert body["prompt"]["13"]["inputs"]["aspect_ratio"] == "9:16 (Portrait Widescreen)"
            return httpx.Response(200, json={"prompt_id": job_id})
        if path.startswith("/history/"):
            return httpx.Response(200, json={job_id: {"status": {"status_str": "success"}, "outputs": {"461": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}}}})
        if path == "/view":
            return httpx.Response(200, content=png)
        raise AssertionError(path)

    async def run():
        settings = Settings(data_dir=tmp_path)
        db = Database(tmp_path)
        session = db.create_session("Japanese, floral", 20)
        graph = json.loads(settings.workflow_path.read_text())
        previous = db.create_generation(session["id"], 20, False, 1, graph)
        db.update(previous["id"], status="complete", prompt="Blue flowers", image_name="previous.png")
        db.save_rating(previous["id"], 70, "Keep the blue flowers.", 20)
        graph["13"]["inputs"]["aspect_ratio"] = "9:16 (Portrait Widescreen)"
        row = db.create_generation(session["id"], 20, False, 0, graph, aspect_ratio="9:16")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            generator = Generator(db, settings, client)
            await generator.run(row["id"])
            assert db.get(row["id"])["status"] == "complete"
            assert (tmp_path / "images" / f"{row['id']}.png").read_bytes() == png
            assert calls.index("/free") < calls.index("/api/chat") < calls.index("/api/generate") < calls.index("/prompt")
            db.update(row["id"], status="error", image_name=None)
            # Retry must preserve the original job even if the session's next ratio changes.
            db.save_rating(previous["id"], 70, "Keep the blue flowers.", 20, "16:9")
            await generator.run(row["id"])
            assert db.get(row["id"])["status"] == "complete"
            assert calls.count("/prompt") == 1
            assert calls.count("/api/chat") == 1

    asyncio.run(run())


def test_llm_output_limit_rejects_incomplete_prompt():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"done_reason": "length"}))) as client:
            with pytest.raises(ValueError, match="response limit"):
                await Ollama(client, "http://ollama", "model").generate({})
    asyncio.run(run())
