# Mubadal

Convert `.pptx` files to `.pdf`. Upload one or many — they convert in parallel.

## Run

```bash
docker compose up --build
```

Then open **http://localhost:4000**.

## How It Works

Upload `.pptx` files via drag-and-drop or file picker. Each file is queued as a Celery task and converted by LibreOffice in headless mode. Four workers run conversions in parallel.

- **1 file** → downloads as `.pdf`
- **Multiple files** → downloads as `.zip`

## Stack

| | |
|---|---|
| Frontend | SvelteKit, served by Nginx on `:4000` |
| Backend | FastAPI on `:8000` |
| Queue | Celery with Redis broker |
| Converter | LibreOffice headless |
| Infra | Docker Compose (4 services) |

## Local Dev (without Docker)

Requires LibreOffice and Redis installed locally.

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# worker
cd backend && celery -A celery_app.celery worker -l info -c 4

# frontend
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

## Endpoints

```
POST /api/convert         → upload 1 file, get task_id
POST /api/convert-batch   → upload N files, get task_ids
GET  /api/task/:id        → poll task status
POST /api/tasks/status    → poll multiple tasks
GET  /api/download/:id    → download single PDF
POST /api/download-batch  → download ZIP of PDFs
GET  /api/health          → health check
```
