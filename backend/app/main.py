import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("memory_lane")


def _warm_up():
    try:
        from app.ai.embeddings import get_embedder
        from app.core.database import migrate_v1_documents
        get_embedder()
        if (n := migrate_v1_documents()):
            log.info("Re-imported %d documents from the v1 database", n)
        if os.getenv("SEED_DEMO", "1").lower() in ("1", "true", "yes") and not settings.TESTING:
            from app.storage.repo import Users
            if not Users.get("user_alex"):
                from app.seed import seed
                log.info("First run: seeding demo archives")
                seed(reset=False)
    except Exception:
        log.exception("Warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="Memory Lane API", version=settings.VERSION, lifespan=lifespan,
              description="Temporal RAG for understanding how your thinking evolves.")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


from app.api import auth, chat, documents, insights, memories, system  # noqa: E402

for r in (auth.router, documents.router, memories.router, chat.router, insights.router, system.router):
    app.include_router(r, prefix=settings.API_PREFIX)

# Serve the built frontend (single-page app) when present
DIST = settings.BASE_DIR / "frontend" / "dist"
if DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
