import asyncio
import time

import httpx


class ComfyUI:
    def __init__(self, client: httpx.AsyncClient, url):
        self.client, self.url = client, url

    async def get(self, path):
        response = await self.client.get(self.url + path)
        response.raise_for_status()
        return response.json()

    async def assert_idle(self):
        queue = await self.get("/queue")
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise ValueError("ComfyUI is busy. Let its current jobs finish, then retry here.")

    async def unload(self):
        await self.assert_idle()
        response = await self.client.post(self.url + "/free", json={"unload_models": True, "free_memory": True})
        response.raise_for_status()
        # /free acknowledges a queued request, not completed unloading.
        await asyncio.sleep(1)
        for _ in range(60):
            stats = await self.get("/system_stats")
            if all(d.get("torch_vram_total", 0) < 64 * 1024 * 1024 for d in stats.get("devices", [])):
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("ComfyUI did not release its GPU memory. Let other jobs finish and retry.")

    async def submit(self, graph, prompt_id):
        await self.assert_idle()
        response = await self.client.post(self.url + "/prompt", json={"prompt": graph, "prompt_id": prompt_id, "client_id": "image-personalizer"}, timeout=30)
        if response.status_code == 400:
            raise ValueError(f"ComfyUI rejected the workflow: {response.text[:1600]}")
        response.raise_for_status()
        return response.json()["prompt_id"]

    async def existing(self, prompt_id):
        history = await self.get(f"/history/{prompt_id}")
        if prompt_id in history:
            return history[prompt_id]
        queue = await self.get("/queue")
        if any(item[1] == prompt_id for item in queue.get("queue_running", []) + queue.get("queue_pending", [])):
            return "running"
        # The job can move from the queue into history between the two reads.
        return (await self.get(f"/history/{prompt_id}")).get(prompt_id)

    @staticmethod
    def image_result(record):
        status = record.get("status", {})
        if status.get("status_str") == "error":
            for event, details in status.get("messages", []):
                if event == "execution_error":
                    raise ValueError(f"ComfyUI: {details.get('exception_message', 'Generation failed.')}")
            raise ValueError("ComfyUI generation was interrupted or failed. Please retry.")
        for output in record.get("outputs", {}).values():
            for image in output.get("images", []):
                if image.get("type") == "output":
                    return image
        raise ValueError("ComfyUI finished without a saved image. Check the workflow's output node.")

    async def wait(self, prompt_id, timeout):
        deadline = time.monotonic() + timeout
        missing = 0
        while time.monotonic() < deadline:
            record = await self.existing(prompt_id)
            if isinstance(record, dict):
                return self.image_result(record)
            missing = missing + 1 if record is None else 0
            if missing >= 10:
                raise ValueError("The ComfyUI job is no longer in its queue or history. Retry to generate it again.")
            await asyncio.sleep(1)
        raise TimeoutError("Image generation is still taking a long time. Retry to reconnect to the same job.")

    async def download(self, image):
        response = await self.client.get(self.url + "/view", params={k: image[k] for k in ("filename", "subfolder", "type")}, timeout=60)
        response.raise_for_status()
        if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("ComfyUI returned an unexpected image format; this workflow should save PNG.")
        return response.content
