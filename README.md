# EKIP

Enterprise Knowledge Intelligence Platform (EKIP) is a full-stack AI/RAG MVP. The application is being built phase by phase according to [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

Phase 0 provides the local Vue, FastAPI, PostgreSQL, and Qdrant foundation. Authentication, document ingestion, and RAG behavior are intentionally not included yet.

## Prerequisites

- Python 3.11 or newer
- Node.js 22 or newer
- Docker Desktop with Docker Compose

## Environment

Create the local environment file from the tracked template:

```powershell
Copy-Item .env.example .env
```

The defaults are intended only for local development. Change credentials and service URLs through environment variables rather than editing application code.

## Local Infrastructure

Start PostgreSQL and Qdrant:

```powershell
docker compose up -d
docker compose ps
```

PostgreSQL listens on `5432` and Qdrant on `6333` by default. Both ports can be changed in `.env`.

## Backend

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Verify the application and its dependencies:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Run backend checks:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest
```

## Frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

The application is available at `http://localhost:5173`.

Run frontend checks:

```powershell
npm run lint
npm run type-check
npm run test
npm run build
```

## Database Migrations

Create schema changes only through Alembic:

```powershell
cd backend
python -m alembic revision --autogenerate -m "describe change"
python -m alembic upgrade head
```

Phase 0 has no application tables, so the initial Alembic revision is intentionally empty.

## Stop Local Infrastructure

```powershell
docker compose down
```

Named Docker volumes preserve local PostgreSQL and Qdrant data. Use `docker compose down --volumes` only when intentionally resetting local data.

