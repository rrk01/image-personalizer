import asyncio
import json
import logging
import secrets
from uuid import uuid4

import httpx

from app.preferences import build_request, is_mutation
from app.services.comfyui import ComfyUI
from app.services.ollama import Ollama

logger = logging.getLogger(__name__)


class Generator:
    def __init__(self, db, settings, client):
        self.db, self.settings = db, settings
        self.comfy = ComfyUI(client, settings.comfyui_url)
        self.ollama = Ollama(client, settings.ollama_url, settings.ollama_model)
        self.task = None

    @property
    def busy(self):
        return self.task is not None and not self.task.done()

    def create(self, session, mutation, rating=None):
        graph = json.loads(self.settings.workflow_path.read_text())
        seed = secrets.randbelow(2**53)
        graph["458"]["inputs"]["seed"] = seed
        row = self.db.create_generation(session["id"], mutation, is_mutation(mutation), seed, graph, rating)
        self.start(row["id"])
        return row

    def start(self, generation_id):
        self.db.update(generation_id, status="preparing", error=None)
        self.task = asyncio.create_task(self.run(generation_id))

    async def run(self, generation_id):
        try:
            row = self.db.get(generation_id)
            prompt_id = row["comfy_prompt_id"]
            existing = await self.comfy.existing(prompt_id) if prompt_id else None
            if isinstance(existing, dict) and existing.get("status", {}).get("status_str") == "error":
                existing = None
            if existing is None:
                if not row["prompt"]:
                    await self.comfy.unload()
                    self.db.update(generation_id, status="prompting")
                    session = self.db.session()
                    request = build_request(self.settings.ollama_model, session["preferences"], self.db.generations(session["id"]), bool(row["mutated"]))
                    self.db.update(generation_id, llm_request_json=json.dumps(request))
                    try:
                        prompt, rationale = await self.ollama.generate(request)
                        self.db.update(generation_id, prompt=prompt, rationale=rationale)
                    finally:
                        await self.ollama.unload()
                else:
                    await self.ollama.unload()
                row = self.db.get(generation_id)
                graph = json.loads(row["workflow_json"])
                graph["452"]["inputs"]["prompt"] = row["prompt"]
                graph["461"]["inputs"]["filename_prefix"] = f"ImagePersonalizer/{generation_id}"
                # Persist the client-generated job ID before sending: network failure
                # after acceptance can then be recovered without duplicating the job.
                prompt_id = str(uuid4())
                self.db.update(generation_id, comfy_prompt_id=prompt_id, workflow_json=json.dumps(graph), status="generating")
                accepted_id = await self.comfy.submit(graph, prompt_id)
                if accepted_id != prompt_id:
                    prompt_id = accepted_id
                    self.db.update(generation_id, comfy_prompt_id=prompt_id)
            else:
                self.db.update(generation_id, status="generating")
            image = await self.comfy.wait(prompt_id, self.settings.image_timeout)
            content = await self.comfy.download(image)
            image_name = f"{generation_id}.png"
            destination = self.settings.data_dir / "images" / image_name
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(destination)
            self.db.update(generation_id, status="complete", image_name=image_name, error=None)
        except asyncio.CancelledError:
            self.db.update(generation_id, status="error", error="The app stopped. Retry to recover this generation.")
            raise
        except Exception as exc:
            logger.exception("Generation %s failed", generation_id)
            if isinstance(exc, httpx.ConnectError):
                message = "Cannot reach a local service. Make sure Ollama and ComfyUI are running, then retry."
            elif isinstance(exc, httpx.TimeoutException):
                message = "A local service timed out. Retry to recover the job or continue."
            elif isinstance(exc, httpx.HTTPStatusError):
                message = f"Local service returned HTTP {exc.response.status_code}: {exc.response.text[:800]}"
            else:
                message = str(exc) or type(exc).__name__
            self.db.update(generation_id, status="error", error=message)

