import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3-vl:8b-instruct-q4_K_M"))
    comfyui_url: str = field(default_factory=lambda: os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/"))
    data_dir: Path = field(default_factory=lambda: (ROOT / os.getenv("DATA_DIR", "data")).resolve())
    workflow_path: Path = ROOT / "workflows/qwen_image_2_1.json"
    image_timeout: float = 1200

