# EKIP

Enterprise Knowledge Intelligence Platform (EKIP) is a full-stack AI/RAG MVP. The application is being built phase by phase according to [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

The current implementation provides the local Vue, FastAPI, PostgreSQL, and Qdrant foundation, email/password authentication for the four demo roles, role-aware document ingestion, grounded adaptive retrieval, SSE answer streaming, persistent conversations, a historical Retrieval Inspector, and explicit RAGAS evaluation runs over a checked-in synthetic corpus.

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

RAGAS evaluation uses `RAGAS_LLM_MODEL` as its judge and
`RAGAS_EMBEDDING_MODEL` for answer relevancy. Evaluation makes multiple OpenAI
requests per case and is run only when an authenticated user explicitly starts it.

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

Open `http://localhost:5173/inspector` to inspect the signed-in user's recent retrieval history. Each query stores immutable chunk snapshots in PostgreSQL, including source metadata, bounded text snippets, pre-rerank rank, strategy-specific dense or RRF scores, ACCURATE reranker score and post-rerank rank, and whether the chunk entered final answer context. FAST stores up to 3 dense candidates, BALANCED up to 8 hybrid RRF candidates, and ACCURATE all available candidates from its initial Top-K 15 retrieval while marking only the final bounded top 5 as context. These snapshots remain available if their original document or conversation is later deleted.

The authenticated inspector endpoints are:

```text
GET /api/queries
GET /api/queries/{query_id}
GET /api/queries/{query_id}/retrieval
```

Every endpoint resolves ownership from the validated JWT and returns the same safe not-found response for missing and other-user query IDs. Snapshot persistence is deliberately observational: a database failure is logged without blocking an otherwise successful grounded answer.

The first ACCURATE query downloads the CPU-compatible FastEmbed BGE reranker model into the local model cache. Later requests reuse the same process-wide model instance.

## RAGAS Evaluation

Apply the latest migration, then seed the versioned synthetic evaluation corpus through
the normal document-ingestion pipeline:

```powershell
cd backend
python -m alembic upgrade head
python -m scripts.seed_evaluation_data
```

The seed command is idempotent and leaves five checked-in Markdown policies indexed
with their intended role metadata. It also ensures the four demo identities exist.
The source documents and 23-case dataset are under `evaluation/`.

Open `http://localhost:5173/evaluations` to run either the representative five-case
set or all 20 cases. The authenticated API endpoints are:

```text
POST /api/evaluations/run
GET  /api/evaluations
GET  /api/evaluations/{run_id}
```

`POST /api/evaluations/run` accepts an optional JSON `case_ids` list; it never accepts
a local file path. A background task runs every case through the existing classifier,
role-filtered retrieval, optional hybrid fusion/reranking, and grounded generation
pipeline without creating conversations. The exact final chunk texts used for answer
generation are passed to RAGAS 0.4 collection metrics for Faithfulness, Answer
Relevancy, Context Precision, and Context Recall. Runs, progress, per-case results,
nullable metric failures, and the original Retrieval Inspector `query_id` are persisted
in PostgreSQL.

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
