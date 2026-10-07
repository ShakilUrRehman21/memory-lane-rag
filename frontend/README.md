# Memory Lane RAG — Frontend Client

Modern, responsive web interface for **Memory Lane RAG** built with React 18, TypeScript, and Vite.

## Features

- **Ask Memory Lane**: Natural language longitudinal querying with citation badges, stance progression, and timeline context.
- **Interactive Timeline**: Multi-year chronological stream with category badges and polarity indicators.
- **Change Explorer**: Trajectory visualization of semantic drift, stance shifts, and detected change-points.
- **Contradiction Inspector**: Detailed view of stance polarity inversions and goal/belief shifts.
- **Version Diff**: Side-by-side comparison of document iterations (e.g. Resume revisions).
- **Temporal Memory Graph**: Visual graph of interconnected temporal memories and relationships.
- **Document Management**: Ingestion studio with file upload (PDF, DOCX, TXT, MD) and live indexing status.
- **Research Studio**: Interactive benchmark workbench evaluating Baseline RAG vs. Temporal RAG vs. Memory Lane RAG.

## Development

```bash
# Install dependencies
npm install

# Start development server (Port 5173, with API proxy to localhost:8000)
npm run dev

# Build production bundle
npm run build
```

See the root [README.md](../README.md) for full project architecture and backend setup.
