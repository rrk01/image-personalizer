import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "personalizer.sqlite3"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "images").mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, preferences TEXT NOT NULL,
                    mutation INTEGER NOT NULL CHECK(mutation BETWEEN 0 AND 100),
                    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_session ON sessions(active) WHERE active=1;
                CREATE TABLE IF NOT EXISTS generations (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    sequence INTEGER NOT NULL, status TEXT NOT NULL,
                    mutation INTEGER NOT NULL, mutated INTEGER NOT NULL,
                    seed INTEGER NOT NULL, prompt TEXT, rationale TEXT,
                    score INTEGER CHECK(score BETWEEN 0 AND 100),
                    image_name TEXT, error TEXT, comfy_prompt_id TEXT,
                    workflow_json TEXT, llm_request_json TEXT,
                    created_at TEXT NOT NULL, rated_at TEXT,
                    UNIQUE(session_id, sequence)
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE active=1").fetchone()
            return dict(row) if row else None

    def create_session(self, preferences, mutation):
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?,1,?)", (str(uuid4()), preferences, mutation, now()))
        return self.session()

    def reset(self):
        with self.connect() as db:
            db.execute("UPDATE sessions SET active=0 WHERE active=1")

    def generations(self, session_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM generations WHERE session_id=? ORDER BY sequence", (session_id,))]

    def get(self, generation_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
            return dict(row) if row else None

    def create_generation(self, session_id, mutation, mutated, seed, workflow, rating=None):
        generation_id = str(uuid4())
        with self.connect() as db:
            if rating:
                db.execute("UPDATE generations SET score=?, rated_at=? WHERE id=?", (rating[1], now(), rating[0]))
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM generations WHERE session_id=?", (session_id,)).fetchone()[0]
            db.execute("""INSERT INTO generations
                (id,session_id,sequence,status,mutation,mutated,seed,workflow_json,created_at)
                VALUES (?,?,?,'preparing',?,?,?,?,?)""",
                (generation_id, session_id, sequence, mutation, int(mutated), seed, json.dumps(workflow), now()))
            db.execute("UPDATE sessions SET mutation=? WHERE id=?", (mutation, session_id))
        return self.get(generation_id)

    def update(self, generation_id, **values):
        allowed = {"status", "prompt", "rationale", "image_name", "error", "comfy_prompt_id", "workflow_json", "llm_request_json"}
        if not values.keys() <= allowed:
            raise ValueError("Unknown generation field")
        with self.connect() as db:
            fields = ",".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE generations SET {fields} WHERE id=?", (*values.values(), generation_id))

    def recover(self):
        with self.connect() as db:
            db.execute("""UPDATE generations SET status='error',
                error='The app stopped during generation. Retry to recover an existing ComfyUI job or continue.'
                WHERE status NOT IN ('complete','error')""")

