from pathlib import Path
from pydantic import BaseModel
import os

class Settings(BaseModel):
    PROJECT_NAME: str = "Memory Lane RAG"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    STORAGE_DIR: Path = DATA_DIR / "storage"
    DB_PATH: Path = STORAGE_DIR / "memory_lane.db"
    UPLOADS_DIR: Path = STORAGE_DIR / "uploads"
    VECTOR_STORE_DIR: Path = STORAGE_DIR / "vectors"

    # LLM & Embedding Settings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 384  # Standard dense embedding dimension
    DEFAULT_LLM_MODEL: str = "gemini-2.5-flash"
    
    # API Keys (optional if running in deterministic local research fixture mode)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Retrieval defaults
    DEFAULT_TOP_K: int = 10
    BM25_WEIGHT: float = 0.35
    SEMANTIC_WEIGHT: float = 0.45
    TEMPORAL_WEIGHT: float = 0.20
    
    # Change detection thresholds
    SEMANTIC_DRIFT_THRESHOLD: float = 0.42
    POLARITY_INVERSION_THRESHOLD: float = 0.75
    
    # Uncertainty window threshold in days (e.g. > 180 days with no docs is uncertain)
    SPARSE_EVIDENCE_DAYS: int = 180

    def ensure_directories(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
