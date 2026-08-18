# EKIP

Enterprise Knowledge Intelligence Platform (EKIP) is a full-stack AI/RAG MVP. The application is being built phase by phase according to [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

The current implementation provides the local Vue, FastAPI, PostgreSQL, and Qdrant foundation, email/password authentication for the four demo roles, role-aware document ingestion, grounded adaptive retrieval, SSE answer streaming, and persistent conversations with historical citation snapshots.

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

Document ingestion and chat require `OPENAI_API_KEY`. Upload limits, chunk size and overlap, embedding, chat, and reranker models, retrieval score threshold, context size, answer size, conversation-history message limit, and the Qdrant collection name are configurable in `.env`. Retrieval Top-K values are centralized in the FAST, BALANCED, and ACCURATE profile definitions.

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

Open `http://localhost:5173/chat` to ask a question against indexed documents available to the authenticated role. Query Intelligence classifies the question as FAQ, specific search, multi-document comparison, summarization, or restricted data, then selects the centralized FAST, BALANCED, or ACCURATE retrieval profile. FAST executes dense Top-K 3. BALANCED executes dense and BM25 sparse retrieval with native Qdrant RRF and returns Top-K 8. ACCURATE retrieves 15 hybrid RRF candidates, reranks them locally with `BAAI/bge-reranker-base`, and supplies only the final Top-K 5 to answer generation. The user's server-resolved role is applied to both Qdrant prefetches before fusion and reranking. Responses include the executed strategy and citations derived from the final authorized chunks supplied as bounded context.

Conversations and messages are persisted in PostgreSQL. The chat workspace lists only the signed-in user's recent conversations, loads message history on selection, derives the title from the first user message, and restores each assistant message with its original JSONB citation snapshot. The current message always runs through retrieval; up to `CHAT_HISTORY_MESSAGE_LIMIT` recent messages are supplied only as conversational generation context and are never treated as authoritative document evidence.

`POST /api/chat/stream` returns standard `text/event-stream` output in this order: `metadata`, incremental `token` events, `citations`, then `complete`. If generation fails after streaming begins, it emits a safe `error` event. User messages are committed before retrieval, while completed assistant messages are committed once after successful generation, avoiding a database transaction across the OpenAI stream. The original non-streaming `POST /api/chat` endpoint remains available through the same RAG preparation path.

Each chat request records its authenticated user, query, classification, selected profile, actual execution strategy, fallback status, and retrieval latency in PostgreSQL. Retrieval latency covers query representations and retrieval, plus reranking for ACCURATE. Apply the latest Alembic migration before using the current chat behavior.

The first ACCURATE query downloads the CPU-compatible FastEmbed BGE reranker model into the local model cache. Later requests reuse the same process-wide model instance.

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

Use the authenticated token to call the chat endpoint directly:

```powershell
$answer = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/chat `
  -Headers @{ Authorization = "Bearer $($login.access_token)" } `
  -ContentType 'application/json' `
  -Body '{"message":"What is the annual leave policy?"}'

$answer
```

Conversation endpoints require the same bearer token:

```powershell
$conversation = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/conversations `
  -Headers @{ Authorization = "Bearer $($login.access_token)" }

Invoke-RestMethod -Uri http://localhost:8000/api/conversations `
  -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

The Vue client consumes the authenticated streaming endpoint with `fetch` and a `ReadableStream`, because the request is a `POST` with an authorization header rather than a native `EventSource` request.

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
