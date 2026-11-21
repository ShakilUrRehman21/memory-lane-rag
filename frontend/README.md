# Memory Lane — web app

React 19 + TypeScript + Vite, with Motion for animation and react-markdown for answers.

```bash
npm install
npm run dev      # http://localhost:5173 (proxies /api to http://127.0.0.1:8000)
npm run build    # type-check + production build into dist/
npm run lint
```

Set `VITE_API_BASE_URL` when the API is hosted on a different origin.

- `src/lib` — API client (incl. SSE streaming), app state & preferences, formatting
- `src/components` — shell, search, quick capture, drawers, UI primitives, ambient background
- `src/views` — Today, Ask, Timeline, Library, Settings
- `src/styles` — design tokens (Dusk & Dawn themes) and view styles
