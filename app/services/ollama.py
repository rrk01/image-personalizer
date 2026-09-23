import asyncio
import json

import httpx


class Ollama:
    def __init__(self, client: httpx.AsyncClient, url, model):
        self.client, self.url, self.model = client, url, model

    async def generate(self, request):
        response = await self.client.post(f"{self.url}/api/chat", json=request, timeout=180)
        response.raise_for_status()
        data = response.json()
        if data.get("done_reason") == "length":
            raise ValueError("The LLM reached its response limit. Retry for a fresh, shorter prompt.")
        try:
            result = json.loads(data["message"]["content"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("The LLM returned an invalid prompt. Please retry.") from exc
        if not isinstance(result, dict) or not all(isinstance(result.get(k), str) and result[k].strip() for k in ("prompt", "rationale")):
            raise ValueError("The LLM returned an empty prompt or explanation. Please retry.")
        if len(result["prompt"]) > 4000 or len(result["rationale"]) > 1200:
            raise ValueError("The LLM response was too long. Please retry.")
        return result["prompt"].strip(), result["rationale"].strip()

    async def unload(self):
        response = await self.client.post(f"{self.url}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=60)
        response.raise_for_status()
        for _ in range(60):
            response = await self.client.get(f"{self.url}/api/ps")
            response.raise_for_status()
            if not any(m.get("name") == self.model or m.get("model") == self.model for m in response.json().get("models", [])):
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("Ollama did not release the model's memory. Close other Ollama chats and retry.")

