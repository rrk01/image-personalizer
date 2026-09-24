import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.preferences import build_request
from app.services.generation import Generator
from app.statistics import score_statistics


@pytest.fixture
def client(tmp_path, monkeypatch):
    async def complete(self, generation_id):
        self.db.update(generation_id, status="complete", prompt="A floral print.", image_name="test.png")
    monkeypatch.setattr(Generator, "run", complete)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        yield client


def test_save_only_edit_then_next_is_atomic_and_idempotent(client):
    first = client.post("/api/generate", json={"preferences": "Floral", "name": "  Prints  "}).json()
    url = f"/api/generations/{first['id']}/rate"
    payload = {"score": 0, "feedback": "  Fewer flowers, please.  ", "mutation": 75, "generate_next": False}
    assert client.post(url, json=payload).status_code == 200
    state = client.get("/api/state").json()
    assert state["generation"]["id"] == first["id"]
    assert state["generation"]["feedback"] == "Fewer flowers, please."
    assert state["session"]["name"] == "Prints"
    assert state["session"]["mutation"] == 75
    assert not state["busy"]
    assert state["statistics"] == {"count": 1, "mean": 0, "best": 0, "standard_deviation": None}
    payload.update(score=60, feedback="Love the soft colors.")
    assert client.post(url, json=payload).status_code == 200
    assert client.get("/api/state").json()["statistics"]["count"] == 1
    payload["generate_next"] = True
    second = client.post(url, json=payload)
    assert second.status_code == 202
    assert second.json()["sequence"] == 2
    payload.update(score=99, feedback="A duplicate must not overwrite the original.")
    assert client.post(url, json=payload).json()["id"] == second.json()["id"]
    saved = client.app.state.db.get(first["id"])
    assert saved["score"] == 60 and saved["feedback"] == "Love the soft colors."
    payload["generate_next"] = False
    assert client.post(url, json=payload).status_code == 409


def test_load_rename_restart_and_context_isolation(client):
    first = client.post("/api/generate", json={"preferences": "Flowers"}).json()
    client.post(f"/api/generations/{first['id']}/rate", json={"score": 80, "feedback": "More blue", "mutation": 0, "generate_next": False})
    first_session = client.get("/api/state").json()["session"]["id"]
    assert client.post(f"/api/sessions/{first_session}/rename", json={"name": "  Blue flowers  "}).status_code == 200
    client.post("/api/reset")
    client.post("/api/generate", json={"preferences": "Architecture", "name": "Buildings"})
    new_session = client.get("/api/state").json()["session"]["id"]
    assert client.post("/api/sessions/missing/load").status_code == 404
    assert client.get("/api/state").json()["session"]["id"] == new_session
    assert client.get("/api/state").json()["statistics"]["count"] == 0
    listing = client.get("/api/sessions").json()
    old = next(s for s in listing if s["id"] == first_session)
    assert old["name"] == "Blue flowers" and old["image_count"] == 1
    assert old["rated_count"] == 1 and old["mean_score"] == 80
    state = client.post(f"/api/sessions/{first_session}/load").json()
    assert state["generation"]["id"] == first["id"]
    assert state["generation"]["feedback"] == "More blue"
    assert state["session"]["mutation"] == 0
    db = client.app.state.db
    with TestClient(create_app(Settings(data_dir=db.path.parent))) as restarted:
        assert restarted.get("/api/state").json() == state
    context = json.loads(build_request("model", "Architecture", db.generations(new_session), False)["messages"][1]["content"])
    assert context["scored_examples"] == []
    assert context["score_statistics"]["count"] == 0


@pytest.mark.parametrize("field,value", [("feedback", "a" * 1001), ("feedback", 5), ("generate_next", "false")])
def test_rating_validation_preserves_unsaved_image(client, field, value):
    first = client.post("/api/generate", json={"preferences": "Flowers"}).json()
    payload = {"score": 50, "mutation": 20, "generate_next": False, field: value}
    assert client.post(f"/api/generations/{first['id']}/rate", json=payload).status_code == 422
    assert client.get("/api/state").json()["generation"]["score"] is None


def test_rename_validation(client):
    client.post("/api/generate", json={"preferences": "Flowers"})
    sid = client.get("/api/state").json()["session"]["id"]
    for name in ["   ", "a" * 81]:
        assert client.post(f"/api/sessions/{sid}/rename", json={"name": name}).status_code == 422
    assert client.post("/api/sessions/missing/rename", json={"name": "Name"}).status_code == 404


def test_statistics_and_llm_use_all_scores_with_recent_feedback():
    assert score_statistics([]) == {"count": 0, "mean": None, "best": None, "standard_deviation": None}
    assert score_statistics([{"score": 40}])["standard_deviation"] is None
    assert score_statistics([{"score": 40}, {"score": 40}])["standard_deviation"] == 0
    assert score_statistics([{"score": n} for n in [0, 50, 100]])["standard_deviation"] == pytest.approx(40.824829)
    rows = [{"id": str(i), "sequence": i, "score": i, "prompt": f"Prompt {i}", "feedback": f"Feedback {i}"} for i in range(101)]
    rows.append({"id": "pending", "sequence": 102, "score": None, "prompt": None})
    request = build_request("model", "Floral", rows, True)
    context = json.loads(request["messages"][1]["content"])
    assert context["score_statistics"] == score_statistics(rows)
    assert context["score_statistics"]["count"] == 101
    assert context["score_statistics"]["mean"] == 50
    assert len(context["scored_examples"]) <= 10
    assert context["scored_examples"][-1]["feedback"] == "Feedback 100"
    assert context["scored_examples"][0]["score"] == 0


@pytest.mark.parametrize("legacy_version", ["original", "feedback"])
def test_legacy_migration_backs_up_once_and_preserves_data(tmp_path, legacy_version):
    # Make the original schema, including its column order, using SQLite DROP COLUMN.
    db = Database(tmp_path)
    session = db.create_session("Flowers " * 15, 20)
    first = db.create_generation(session["id"], 20, False, 42, {"original": "workflow"})
    db.update(first["id"], status="complete", prompt="Original prompt", image_name="original.png")
    feedback = "" if legacy_version == "original" else "Keep the blue flowers."
    db.save_rating(first["id"], 0, feedback, 20)
    (tmp_path / "images" / "original.png").write_bytes(b"original-image")
    with db.connect() as conn:
        if legacy_version == "original":
            conn.execute("ALTER TABLE sessions DROP COLUMN name")
            conn.execute("ALTER TABLE generations DROP COLUMN feedback")
        conn.execute("ALTER TABLE sessions DROP COLUMN aspect_ratio")
        conn.execute("ALTER TABLE generations DROP COLUMN aspect_ratio")
        before_sessions = [dict(r) for r in conn.execute("SELECT * FROM sessions")]
        before_generations = [dict(r) for r in conn.execute("SELECT * FROM generations")]
    upgraded = Database(tmp_path)
    assert upgraded.session()["name"] == session["preferences"][:80]
    assert upgraded.get(first["id"])["feedback"] == feedback
    assert upgraded.session()["aspect_ratio"] == upgraded.get(first["id"])["aspect_ratio"] == "1:1"
    assert {k: upgraded.session()[k] for k in before_sessions[0]} == before_sessions[0]
    assert {k: upgraded.get(first["id"])[k] for k in before_generations[0]} == before_generations[0]
    assert (tmp_path / "images" / "original.png").read_bytes() == b"original-image"
    Database(tmp_path)
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert "aspect_ratio" not in {r[1] for r in backup.execute("PRAGMA table_info(generations)")}
        assert backup.execute("SELECT score FROM generations").fetchone()[0] == 0


def test_app_factory_does_not_touch_database_before_startup(tmp_path):
    path = tmp_path / "not-created"
    create_app(Settings(data_dir=path))
    assert not path.exists()


@pytest.mark.parametrize("ratio,width,height", [
    ("1:1", 1024, 1024), ("2:3", 832, 1248), ("3:2", 1248, 832),
    ("3:4", 880, 1184), ("4:3", 1184, 880), ("9:16", 768, 1360),
    ("16:9", 1360, 768), ("21:9", 1568, 672),
])
def test_aspect_ratio_reaches_workflow_and_display(client, ratio, width, height):
    from app.aspect_ratios import ASPECT_RATIOS
    response = client.post("/api/generate", json={"preferences": "Flowers", "aspect_ratio": ratio})
    assert response.status_code == 202
    first = response.json()
    assert first["image_format"]["width"] == width
    assert first["image_format"]["height"] == height
    graph = json.loads(client.app.state.db.get(first["id"])["workflow_json"])
    assert graph["13"]["inputs"] == {"aspect_ratio": ASPECT_RATIOS[ratio], "megapixels": 1, "multiple": 16}
    assert graph["456"]["inputs"]["width"] == ["13", 0]
    assert graph["456"]["inputs"]["height"] == ["13", 1]
    state = client.get("/api/state").json()
    assert state["session"]["aspect_ratio"] == state["generation"]["aspect_ratio"] == ratio
    assert len(state["aspect_ratios"]) == 8


def test_next_ratio_saves_separately_from_current_image_and_reopens(client):
    first = client.post("/api/generate", json={"preferences": "Flowers", "aspect_ratio": "2:3"}).json()
    url = f"/api/generations/{first['id']}/rate"
    payload = {"score": 80, "mutation": 20, "feedback": "Try wider framing", "aspect_ratio": "16:9", "generate_next": False}
    assert client.post(url, json=payload).status_code == 200
    state = client.get("/api/state").json()
    sid = state["session"]["id"]
    assert state["session"]["aspect_ratio"] == "16:9"
    assert state["generation"]["aspect_ratio"] == "2:3"
    client.post("/api/reset")
    assert client.post(f"/api/sessions/{sid}/load").json() == state
    with TestClient(create_app(Settings(data_dir=client.app.state.db.path.parent))) as restarted:
        assert restarted.get("/api/state").json() == state
    payload.pop("aspect_ratio")  # Older clients inherit the saved session ratio.
    payload["generate_next"] = True
    second = client.post(url, json=payload).json()
    assert second["aspect_ratio"] == "16:9"
    payload["aspect_ratio"] = "9:16"
    assert client.post(url, json=payload).json()["id"] == second["id"]
    assert client.get("/api/state").json()["session"]["aspect_ratio"] == "16:9"
    assert client.app.state.db.get(first["id"])["aspect_ratio"] == "2:3"
    context = json.loads(build_request("model", "Flowers", client.app.state.db.generations(sid), False, "16:9")["messages"][1]["content"])
    assert context["image_format"]["aspect_ratio"] == "16:9"
    assert context["scored_examples"][0]["aspect_ratio"] == "2:3"


@pytest.mark.parametrize("ratio", ["0:1", "4:5", "1:1 (Square)", "", 1])
def test_invalid_ratio_does_not_save_rating_or_create_session(client, ratio):
    assert client.post("/api/generate", json={"preferences": "Flowers", "aspect_ratio": ratio}).status_code == 422
    assert client.get("/api/state").json()["session"] is None
    first = client.post("/api/generate", json={"preferences": "Flowers"}).json()
    assert first["aspect_ratio"] == "1:1"
    response = client.post(f"/api/generations/{first['id']}/rate", json={"score": 80, "mutation": 20, "aspect_ratio": ratio})
    assert response.status_code == 422
    assert client.get("/api/state").json()["generation"]["score"] is None
