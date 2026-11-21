"""Start the Memory Lane API (and the built web app, if `frontend/dist` exists)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    from app.core.config import settings  # noqa: F401  (loads .env)

    here = str(Path(__file__).resolve().parent)
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                app_dir=here, reload=os.getenv("RELOAD", "").lower() in ("1", "true"), reload_dirs=[here])
