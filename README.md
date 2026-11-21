# Memory Lane

**A private, time-aware companion for your journals and documents.**
Ask how your thinking changed, find the turning points, notice the tensions, and see what has always stayed the same — every answer grounded in your own words, with dates and sources you can open.

Memory Lane is a *temporal* RAG system: it doesn't just find similar passages, it understands **when** each thought happened and reasons across time.

---

## What's inside

| Page | What it's for |
|---|---|
| **Today** | A greeting, one box to ask anything, *On this day* memories, and how your views have changed |
| **Ask** | Ask your past self a question. Answers stream in, and every `[n]` opens the exact entry it came from |
| **Timeline** | All your memories in the order they happened. Search, or filter by topic |
| **Library** | Drop in journals, notes or documents (PDF, Word, text, Markdown and more), or write a note |
| **Settings** | Light/dark theme, profile, backup & restore, password |

Shortcuts: `Ctrl K` to search, `Ctrl J` to write a quick thought.

## Quick start (Windows)

Double-click **`start.bat`**. That's it.

The first run sets everything up (Python environment, packages, web app) and takes a few minutes; after that it starts in seconds and opens your browser at http://127.0.0.1:8000. Keep the window open while you use Memory Lane, and close it to stop.

You need [Python 3.10+](https://www.python.org/downloads/) (tick *Add python.exe to PATH*) and [Node.js LTS](https://nodejs.org/) installed once.

Try the demo by clicking one of the demo people on the sign-in screen (password `password123`), or create your own account.

After adding API keys to `.env`, double-click **`test-keys.bat`** to check they work: it sends each provider a one-word question, then asks a real question about the demo archive.

`dev.bat` is for editing the code: it runs the API and web app with live reload in two windows (http://localhost:5173).

### Manual start (macOS / Linux)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm install && npm run build)
python backend/run.py           # http://127.0.0.1:8000
```

**Docker:** `docker compose up --build` → http://localhost:8000.

## Answer quality: models & embeddings

| Setting | What happens |
|---|---|
| No keys | Answers come from the built-in **offline writer**: chronological and fully cited. |
| `GEMINI_API_KEY` or `OPENAI_API_KEY` | Streaming, conversational answers from that model, grounded in numbered evidence. |
| `OLLAMA_URL` | Same, using a local model through Ollama. |
| Embeddings (`EMBEDDINGS=auto`) | Uses **fastembed** (`bge-small-en-v1.5`, ~70 MB, downloaded once, runs locally). Falls back to Gemini/OpenAI embeddings, then to a built-in lexical-semantic embedder. Switching providers re-indexes automatically. |

The bottom of the Settings page shows which model is writing your answers.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest            # 24 tests: auth & isolation, ingestion, dates, retrieval, chat streaming, export/import, benchmark
cd frontend && npm run build   # type-check + production build
```

## Upgrading from v1

The first start archives the old database as `data/storage/memory_lane.v1-backup.db`, carries over real accounts (passwords keep working and are upgraded on next sign-in), re-imports their documents, and re-seeds the demo archives. Test accounts are not carried over.

## Project layout

```
backend/app/
  core/        config (.env), SQLite schema & migration, auth & rate limiting
  ingestion/   parsers, date grounding, chunking, memory extraction, pipeline
  ai/          embeddings (fastembed / API / local) and streaming LLM adapters
  storage/     repository (users, documents, memories, chats…) and vector index
  retrieval/   query understanding and hybrid temporal retrieval
  reasoning/   change points, contradictions, graph edges, version diff, insights
  synthesis/   grounded, cited answer generation + offline writer
  evaluation/  benchmark corpus and runner
  api/         FastAPI routes
frontend/src/
  lib/         API client (SSE streaming), app state, formatting
  components/  shell, search & capture, detail drawers, UI primitives, ambient background
  views/       Today, Ask, Timeline, Library, Settings
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for how it works and [DEPLOYMENT.md](DEPLOYMENT.md) for hosting.

## License

MIT
