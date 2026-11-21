"""Central configuration. Values come from environment variables or a `.env` file at the project root."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

try:  # load .env before reading any setting
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # python-dotenv is optional
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Settings:
    PROJECT_NAME = "Memory Lane"
    VERSION = "2.0.0"
    API_PREFIX = "/api"

    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = Path(_env("MEMORY_LANE_DATA_DIR") or BASE_DIR / "data")

    @property
    def STORAGE_DIR(self) -> Path:
        return self.DATA_DIR / "storage"

    @property
    def DB_PATH(self) -> Path:
        return self.STORAGE_DIR / "memory_lane.db"

    @property
    def UPLOADS_DIR(self) -> Path:
        return self.STORAGE_DIR / "uploads"

    @property
    def MODEL_CACHE_DIR(self) -> Path:
        return self.STORAGE_DIR / "models"

    # ---- LLM providers (first configured one wins unless LLM_PROVIDER is set) ----
    LLM_PROVIDER = _env("LLM_PROVIDER", "auto")  # auto | gemini | openai | ollama | offline
    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODELS = _env("GEMINI_FALLBACK_MODELS")  # optional, comma-separated; auto-detected if empty
    GEMINI_ENDPOINT = _env("GEMINI_ENDPOINT")  # optional: force AI Studio or Vertex express base URL
    OPENAI_API_KEY = _env("OPENAI_API_KEY")
    OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OLLAMA_URL = _env("OLLAMA_URL")  # e.g. http://localhost:11434
    OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.1")
    LLM_TIMEOUT = float(_env("LLM_TIMEOUT", "60"))

    # ---- Embeddings ----
    EMBEDDINGS = _env("EMBEDDINGS", "auto")  # auto | fastembed | gemini | openai | local
    FASTEMBED_MODEL = _env("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")

    # ---- Retrieval ----
    DEFAULT_TOP_K = 12
    RRF_K = 60
    MMR_LAMBDA = 0.72

    # ---- Reasoning thresholds ----
    SEMANTIC_DRIFT_THRESHOLD = 0.45
    POLARITY_FLIP_MIN_GAP = 0.8
    SPARSE_EVIDENCE_DAYS = 180

    # ---- Limits & security ----
    MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "25"))
    SESSION_DAYS = int(_env("SESSION_DAYS", "30"))
    CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "*").split(",") if o.strip()]
    TESTING = _env_bool("MEMORY_LANE_TESTING")

    def ensure_directories(self) -> None:
        for p in (self.DATA_DIR, self.STORAGE_DIR, self.UPLOADS_DIR, self.MODEL_CACHE_DIR):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
