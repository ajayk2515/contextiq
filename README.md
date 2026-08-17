# EKIP

Enterprise Knowledge Intelligence Platform (EKIP) is a full-stack AI/RAG MVP. The application is being built phase by phase according to [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

The current implementation provides the local Vue, FastAPI, PostgreSQL, and Qdrant foundation, email/password authentication for the four demo roles, and role-aware document ingestion. Retrieval and RAG behavior are intentionally not included yet.

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

Document ingestion requires `OPENAI_API_KEY` for dense embeddings. Upload limits, chunk size and overlap, embedding model and dimensions, and the Qdrant collection name are configurable in `.env`.

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
python -m scripts.seed_demo
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

The first PDF parsing run downloads Docling model assets into a local ignored cache. On Windows, the application uses Hugging Face's no-symlink cache fallback and disables Torch model compilation, so Visual C++ build tools are not required.

## Frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

The application is available at `http://localhost:5173`.

After signing in, open `http://localhost:5173/documents` to upload a PDF, DOCX, PPTX, or Markdown file and assign its allowed roles. Documents move from `PROCESSING` to `READY` after Docling parsing, dense and sparse embedding, and Qdrant indexing. Failed processing stores a visible error message.

## Demo Authentication

The seed command is idempotent and creates or refreshes these local accounts:

| Email | Role |
| --- | --- |
| `developer@demo.com` | Developer |
| `hr@demo.com` | HR |
| `finance@demo.com` | Finance |
| `executive@demo.com` | Executive |

All demo users receive the password configured in `DEMO_USER_PASSWORD`. The checked-in example uses `ekip_demo_password` for local development only. Never reuse that value outside a local demo environment.

Authentication uses a signed JWT access token. The browser stores the token in `sessionStorage`, so it survives a normal page refresh but is removed when the user signs out or the browser session ends. Configure `JWT_SECRET` with a unique value of at least 32 characters.

Verify authentication from PowerShell:

```powershell
$login = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/auth/login `
  -ContentType 'application/json' `
  -Body '{"email":"developer@demo.com","password":"ekip_demo_password"}'

Invoke-RestMethod -Uri http://localhost:8000/api/auth/me `
  -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

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
