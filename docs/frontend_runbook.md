# Frontend runbook (Tenacious Ops)

Next.js app in `web/`: **dark / light / system** themes, **blue** primary, Tailwind v4. Talks to the FastAPI **orchestration** app (`agent/api/orchestration_app.py`).

## Prerequisites

- Node.js 20+ and npm
- Python env with `agent/requirements.txt` installed
- Repo `.env` (or `.env.example` copy) for enrichment paths, optional `ORCHESTRATION_API_KEY`
- **CORS:** The UI defaults to a **same-origin proxy** (`/api/orchestration` → FastAPI). The FastAPI app also **merges local Next dev origins** (`localhost:3000`, `127.0.0.1:3000`) when `ORCHESTRATION_CORS_ALLOW_LOCALHOST_DEV` is true (default in `.env.example`), so direct browser→uvicorn URLs work without editing the Connection screen. Set that flag to `false` in production if you want a strict allow-list only.

## 1) Start the orchestration API

From the `agent/` directory (so the `agent` package resolves):

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\agent"
python -m uvicorn agent.api.orchestration_app:app --host 127.0.0.1 --port 8000
```

**CORS:** If the UI runs on another origin (e.g. `http://localhost:3000`), set in `.env`:

```env
ORCHESTRATION_CORS_ORIGINS=http://localhost:3000
```

**API key:** If `ORCHESTRATION_API_KEY` is set in `.env`, every orchestration route except `/health` and OpenAPI requires `X-API-Key` — enter the same value on the UI **Connection** page.

## 2) Start the Next.js dev server

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\web"
Copy-Item .env.local.example .env.local   # sets ORCHESTRATION_UPSTREAM_URL → uvicorn
npm install
npm run dev
```

Open **http://localhost:3000** — **Overview** (`/`) explains the system and stages; **Pipeline** (`/pipeline`) runs intake. Company choices load from **`GET /api/companies`** (reads the repo Crunchbase CSV; override path with **`CRUNCHBASE_DATASET_PATH`** in `web/.env.local` if needed).

The app calls **`/api/orchestration/...`** on the Next server; **`next.config.ts`** rewrites those to **`ORCHESTRATION_UPSTREAM_URL`** (default `http://127.0.0.1:8000/...`), so the browser never cross-posts to another origin and CORS does not apply.

## 3) Use the UI

1. **Connection** (`/login`): default API base is **`/api/orchestration`** (proxy). Optional API key → **localStorage** only.
2. **Pipeline**: health check + **Process new lead** (`POST /lead/process`). The progress bar tracks stages by polling session/state during execution.
3. **Pipeline runs** table lists existing company pipelines (`GET /pipelines`) with **Open** and **Delete** actions (`DELETE /pipelines/{lead_id}`).
4. After success, you land on **Lead detail** with human-friendly stage/score/evidence summaries (no raw JSON dump).
5. **Theme** toggle in header cycles light → dark → system.

## 4) Production build

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\web"
npm run build
npm run start
```

Point `NEXT_PUBLIC_ORCHESTRATION_API_URL` at your deployed API URL; keep secrets out of client bundles (use Connection page or a future server-side BFF).

## 5) Quality checks

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\web"
npm run lint
```

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| CORS error in browser | Prefer default **proxy** base `/api/orchestration`. If you use a full `http://127.0.0.1:8000` URL in Connection, add **`http://localhost:3000`** (not `127.0.0.1:3000` unless that is your real origin) to `ORCHESTRATION_CORS_ORIGINS` and restart uvicorn. |
| 401 from API | Clear Connection key or set it to match `ORCHESTRATION_API_KEY`. |
| Health fails | Confirm uvicorn URL/port matches Connection base URL. |
| Process lead hangs / errors | Check agent logs; ensure dataset paths in `.env` match machine (Crunchbase CSV, etc.). |
