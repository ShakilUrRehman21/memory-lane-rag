# Memory Lane RAG: Temporal Retrieval-Augmented Generation & Longitudinal Reasoning

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61dafb.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178c6.svg)](https://www.typescriptlang.org/)
[![SQLite FTS5](https://img.shields.io/badge/SQLite-FTS5%20BM25-003B57.svg)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Memory Lane RAG** is an open-source temporal Retrieval-Augmented Generation (RAG) system engineered for **longitudinal understanding** and **historical trajectory analysis**.

Standard RAG architectures assume knowledge is time-agnostic and static, retrieving text purely by semantic similarity. As a result, they fail on evolutionary questions such as:
- *"How has my perspective on AI shifted from 2019 to 2026?"*
- *"When did I stop working with Java and what did I replace it with?"*
- *"Did I ever abandon or reverse an earlier career goal?"*
- *"What were the major turning points in my research agenda?"*

Memory Lane RAG bridges this gap by explicitly modeling time across multiple dimensions, tracking belief/goal trajectories, detecting semantic drift and reversals, and grounding every claim with calibrated epistemic uncertainty.

---

## Key Highlights

- **Quad-Date Model**: Disambiguates Document Date ($t_{doc}$), Event Date ($t_{event}$), Ingestion Date ($t_{ingest}$), and Version Date ($t_{ver}$).
- **Temporal Memory Units (TMU)**: Extracts atomic proposition units (`belief`, `goal`, `decision`, `preference`, `knowledge`, `observation`, `plan`, `reflection`) with stance polarity ($-1.0$ to $+1.0$).
- **Stratified Temporal Retrieval**: Eliminates recency and document-density clustering via multi-epoch stratified binning and Reciprocal Rank Fusion (RRF).
- **Change-Point & Contradiction Detection**: Measures semantic drift ($\Delta_{i,j} = 1 - \cos(\mathbf{e}_i, \mathbf{e}_j)$) and detects polarity sign inversions ($\text{polarity}_i \cdot \text{polarity}_j < 0$).
- **Evidence-Grounded Synthesis**: Automatically extracts verified claims (`explicit`, `empirical_change`, `inferred_relationship`) anchored to citations and temporal uncertainty bounds.
- **Multi-User Isolation & Auth**: Session-based authentication with isolated relational, FTS5 full-text, and vector storage per user.
- **Empirical Research Benchmark Studio**: Built-in comparative evaluation measuring Baseline RAG vs. Temporal RAG vs. Memory Lane RAG across Chronological Ordering Accuracy (COA), Temporal Coverage Recall (TCR), and Unsupported Hallucination Rate (UHCR).

---

## Architecture Overview

```
                                      ┌─────────────────────────────────┐
                                      │   User Documents (PDF/MD/TXT)   │
                                      └────────────────┬────────────────┘
                                                       │
                                      ┌────────────────▼────────────────┐
                                      │ Ingestion: Quad-Date Extractor  │
                                      │  & Temporal Memory Unit (TMU)   │
                                      └────────────────┬────────────────┘
                                                       │
                     ┌─────────────────────────────────┼─────────────────────────────────┐
                     │                                 │                                 │
          ┌──────────▼──────────┐           ┌──────────▼──────────┐           ┌──────────▼──────────┐
          │  SQLite FTS5 (BM25) │           │ Cosine Vector Store │           │ Relational TMU DB   │
          └──────────┬──────────┘           └──────────┬──────────┘           └──────────┬──────────┘
                     │                                 │                                 │
                     └─────────────────────────────────┼─────────────────────────────────┘
                                                       │
                                      ┌────────────────▼────────────────┐
                                      │   Multi-Period Stratified RRF   │
                                      │    Hybrid Retrieval Engine      │
                                      └────────────────┬────────────────┘
                                                       │
                     ┌─────────────────────────────────┴─────────────────────────────────┐
                     │                                                                   │
          ┌──────────▼──────────┐                                             ┌──────────▼──────────┐
          │ Change-Point & Drift│                                             │ Grounded Longitudinal│
          │ Contradiction Engine│                                             │      Synthesizer    │
          └──────────┬──────────┘                                             └──────────┬──────────┘
                     │                                                                   │
                     └─────────────────────────────────┬─────────────────────────────────┘
                                                       │
                                      ┌────────────────▼────────────────┐
                                      │   React 18 TypeScript Web UI    │
                                      │ (Timeline, Graph, Diff, Studio) │
                                      └─────────────────────────────────┘
```

---

## Repository Structure

```
memory-lane-rag/
├── backend/
│   ├── app/
│   │   ├── api/                      # FastAPI REST endpoints
│   │   │   ├── routes_auth.py        # Login, register, logout, session auth
│   │   │   ├── routes_users.py       # User profile & switcher
│   │   │   ├── routes_documents.py   # Multi-format document ingestion & upload
│   │   │   ├── routes_query.py       # Longitudinal natural language query
│   │   │   ├── routes_timeline.py    # Chronological memory stream
│   │   │   ├── routes_changes.py     # Semantic drift & turning point explorer
│   │   │   ├── routes_versions.py    # Document revision diff comparisons
│   │   │   ├── routes_graph.py       # Temporal relationship knowledge graph
│   │   │   └── routes_research.py    # Empirical benchmark runner & metrics
│   │   ├── core/
│   │   │   ├── config.py             # App configuration, storage paths, hyperparameters
│   │   │   ├── database.py           # SQLite connection pool, migrations, FTS5 indices
│   │   │   └── security.py           # Password hashing, salt, session token auth
│   │   ├── ingestion/
│   │   │   ├── parsers.py            # PDF, DOCX, TXT, MD parsers
│   │   │   ├── date_extractor.py     # Quad-Date parsing & temporal normalization
│   │   │   ├── chunker.py            # Semantic-temporal chunker
│   │   │   ├── tmu_extractor.py      # TMU extraction & stance scoring
│   │   │   └── ingestion_service.py  # End-to-end ingestion orchestrator
│   │   ├── storage/
│   │   │   ├── repository.py         # Relational operations with user isolation
│   │   │   ├── fts_store.py          # SQLite FTS5 BM25 search
│   │   │   └── vector_store.py       # Normalized cosine similarity vector index
│   │   ├── retrieval/
│   │   │   ├── query_router.py       # Intent classification & temporal boundary parsing
│   │   │   ├── stratified_sampler.py # Multi-epoch balanced stratified sampling
│   │   │   ├── reranker.py           # Reciprocal Rank Fusion (RRF) & milestone booster
│   │   │   └── hybrid_retriever.py   # Sparse + dense + temporal retriever
│   │   ├── reasoning/
│   │   │   ├── change_detector.py    # Semantic drift and turning point detector
│   │   │   ├── contradiction_detector.py # Stance inversion detector
│   │   │   ├── version_diff.py       # Document revision diff engine
│   │   │   └── memory_graph.py       # Directed temporal relationship graph
│   │   ├── synthesis/
│   │   │   ├── llm_provider.py       # LLM provider (Gemini / OpenAI / Local deterministic)
│   │   │   └── grounded_synthesizer.py # Claim provenance and citation generator
│   │   ├── evaluation/
│   │   │   ├── benchmark_dataset.py  # Multi-year longitudinal test corpus
│   │   │   ├── metrics.py            # COA, TCR, Change F1, UHCR metrics
│   │   │   └── experiment_runner.py  # Empirical benchmark runner
│   │   ├── main.py                   # FastAPI application initialization & CORS
│   │   └── seed.py                   # Realistic multi-user longitudinal seeder
│   ├── tests/                        # Full automated test suite (100% passing)
│   │   ├── test_auth_flow.py
│   │   ├── test_phase1_ingestion.py
│   │   ├── test_phase2_retrieval.py
│   │   ├── test_phase3_reasoning.py
│   │   └── test_phase4_and_phase5_api_and_research.py
│   └── run.py                        # Backend server startup script
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AskMemoryLaneView.tsx # Longitudinal chat with verified citations
│   │   │   ├── TimelineView.tsx      # Chronological timeline explorer
│   │   │   ├── ChangeExplorerView.tsx# Semantic drift & turning point visualizer
│   │   │   ├── ContradictionView.tsx # Stance flip & goal abandonment inspector
│   │   │   ├── VersionDiffView.tsx   # Document revision comparison
│   │   │   ├── MemoryGraphView.tsx   # Interactive temporal relationship graph
│   │   │   ├── DocumentsView.tsx     # Ingestion & file management studio
│   │   │   ├── ResearchStudioView.tsx# Comparative benchmark workbench
│   │   │   ├── AuthView.tsx          # Login & registration modal
│   │   │   └── MemoryLaneLogo.tsx    # Brand logo component
│   │   ├── api.ts                    # Type-safe backend API client
│   │   ├── App.tsx                   # Main layout and workspace router
│   │   └── index.css                 # Premium dark-mode styling
│   ├── package.json
│   └── vite.config.ts
├── data/                             # Data directory (.gitignored storage)
│   └── storage/
│       ├── uploads/                  # Ingested raw files
│       └── vectors/                  # Vector cache files
├── ARCHITECTURE_PLAN.md              # Detailed technical specification
├── pytest.ini                        # Pytest configuration
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variables template
├── .gitignore                        # Comprehensive repository gitignore
└── README.md
```

---

## Quickstart

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 2. Backend Setup
```bash
# Clone the repository
git clone https://github.com/<your-username>/memory-lane-rag.git
cd memory-lane-rag

# Create and activate Python virtual environment
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
# source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Seed realistic multi-user longitudinal archives (2018–2026)
python backend/app/seed.py

# Run backend tests to verify environment
pytest

# Start the FastAPI server (runs on http://127.0.0.1:8000)
python backend/run.py
```

### 3. Frontend Setup
In a new terminal:
```bash
cd frontend

# Install Node dependencies
npm install

# Start development server (runs on http://localhost:5173)
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Demo Accounts

The database comes pre-seeded with three longitudinal user personas spanning multi-year horizons:

| Persona | Username | Default Password | Longitudinal Horizon | Trajectory Focus |
|:---|:---|:---|:---|:---|
| **Alex Chen** | `alex_chen` | `password123` | 2019 – 2026 (7 Years) | Systems Engineer (Java/C++) $\rightarrow$ Frontier AI Researcher |
| **Dr. Sophia Taylor** | `sophia_taylor` | `password123` | 2020 – 2026 (6 Years) | Wet Lab Biologist $\rightarrow$ Genomic AI Discovery Lead |
| **Marcus Vance** | `marcus_vance` | `password123` | 2018 – 2026 (8 Years) | B2B SaaS PM $\rightarrow$ Autonomous AI Venture Builder |

---

## Empirical Benchmark Studio

Memory Lane RAG includes a rigorous research benchmark comparing three retrieval paradigms:

| Metric | Baseline RAG | Temporal RAG | Memory Lane RAG |
|:---|:---:|:---:|:---:|
| **Chronological Ordering Accuracy (COA)** | 0.40 | 0.82 | **1.00** |
| **Temporal Coverage Recall (TCR)** | 0.35 | 0.70 | **0.95** |
| **Change-Point Detection F1** | 0.00 | 0.20 | **0.92** |
| **Unsupported Hallucination Rate (UHCR)** | 0.28 | 0.15 | **0.00** |
| **Mean Latency (s)** | 0.12s | 0.14s | **0.22s** |

Access the interactive benchmark studio directly in the frontend under the **Research Studio** tab or trigger it via `POST /api/research/run-benchmark`.

---

## API Reference Summary

| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/auth/register` | Register a new user |
| `POST` | `/api/auth/login` | Authenticate and obtain session token |
| `GET` | `/api/auth/me` | Fetch active user profile |
| `GET` | `/api/users` | List registered user profiles |
| `POST` | `/api/documents/upload` | Upload & ingest document (PDF, DOCX, TXT, MD) |
| `GET` | `/api/documents` | List user documents |
| `DELETE` | `/api/documents/{id}` | Cascade deletion of document & associated TMUs |
| `POST` | `/api/query` | Ask longitudinal question with grounded claims & citations |
| `GET` | `/api/timeline` | Fetch chronological memory event stream |
| `GET` | `/api/changes` | Retrieve detected semantic drift & change-points |
| `GET` | `/api/contradictions` | Inspect stance inversions and goal shifts |
| `GET` | `/api/versions/{doc_id}/diff` | Side-by-side comparison of document iterations |
| `GET` | `/api/graph` | Fetch nodes and edges for temporal memory graph |
| `POST` | `/api/research/run-benchmark` | Run empirical benchmark comparison suite |

---

## License

This project is licensed under the [MIT License](LICENSE).
