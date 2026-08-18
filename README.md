# EKIP

Enterprise Knowledge Intelligence Platform (EKIP) is a role-aware knowledge assistant that
turns internal documents into grounded, cited answers. It combines adaptive retrieval,
authorization inside the vector query, persistent conversations, retrieval explainability,
explicit RAG evaluation, deterministic optimization guidance, and aggregate analytics in one
modular monolith.

The application is complete for local MVP use through Phase 12 of
[`PROJECT_SPEC.md`](PROJECT_SPEC.md). Cloud deployment is intentionally reserved for Phase 13.

## Key Features

- Email/password authentication with signed JWT access tokens and four demo roles
- PDF, DOCX, PPTX, and Markdown ingestion through Docling
- Dense OpenAI embeddings and FastEmbed BM25-compatible sparse vectors in Qdrant
- Qdrant payload filtering by the server-resolved role before candidate selection
- Query Intelligence that selects FAST, BALANCED, or ACCURATE retrieval
- Dense search, hybrid retrieval, native reciprocal rank fusion (RRF), and local BGE reranking
- Grounded OpenAI answers with citations and explicit insufficient-context behavior
- SSE answer streaming and PostgreSQL-backed conversations
- Historical Retrieval Inspector with immutable candidate snapshots
- Explicit RAGAS evaluation for Faithfulness, Answer Relevancy, Context Precision, and Context Recall
- Persisted, deterministic optimization recommendations that never auto-apply changes
- Authenticated analytics for quality, strategy usage, latency, and open recommendations

## Architecture

```text
Vue 3 + Pinia + ECharts
          |
       REST / SSE
          |
       FastAPI
       |   |   |
       |   |   +-- OpenAI chat and dense embeddings
       |   +------ Qdrant dense/sparse vectors and RBAC filters
       +---------- PostgreSQL application, retrieval, evaluation, and analytics data
          |
          +------ Docling ingestion / FastEmbed sparse vectors / local BGE reranker / RAGAS
```

The backend is a modular monolith: authentication, documents, ingestion, retrieval, chat,
conversations, inspection, evaluation, optimization, and analytics have separate modules while
sharing one FastAPI process and PostgreSQL transaction boundary. This keeps the MVP deployable as
one service without introducing distributed-system overhead.

### Request Flow

```text
Authenticated question
  -> classify category and retrieval profile
  -> apply the user's server-resolved role in Qdrant
  -> dense or dense+sparse retrieval
  -> optional RRF and BGE reranking
  -> bounded authorized context
  -> grounded streamed answer and citations
  -> persist query/retrieval facts and conversation messages
  -> expose aggregate trends through Analytics
```

## Technology Stack

| Area | Technology |
| --- | --- |
| Frontend | Vue 3, TypeScript, Pinia, Vue Router, Tailwind CSS, ECharts, Vitest |
| Backend | FastAPI, Pydantic, SQLAlchemy async, Alembic, pytest |
| Data | PostgreSQL 16, Qdrant |
| AI and ingestion | OpenAI API, Docling, FastEmbed, BGE reranker |
| Evaluation | RAGAS 0.4, deterministic optimization rules |
| Local services | Docker Compose |

## Prerequisites

- Python 3.11 or newer
- Node.js 22 or newer
- Docker Desktop with Docker Compose
- An OpenAI API key for ingestion, chat, Query Intelligence, and evaluation

## Local Setup

Create the environment file and add a valid `OPENAI_API_KEY` locally:

```powershell
Copy-Item .env.example .env
```

Start PostgreSQL and Qdrant:

```powershell
docker compose up -d
docker compose ps
```

Set up and start the backend from the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m scripts.seed_demo
python -m scripts.seed_evaluation_data
python -m uvicorn app.main:app --reload
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The API is at `http://localhost:8000`, interactive OpenAPI
documentation is at `http://localhost:8000/docs`, and health is at
`http://localhost:8000/health`.

## Environment Variables

`.env.example` contains every application setting with safe local or blank values. `.env` is
ignored by Git. Important groups are:

| Purpose | Variables |
| --- | --- |
| Application | `APP_ENV`, `CORS_ORIGINS`, `VITE_API_BASE_URL` |
| Authentication | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES`, `JWT_ISSUER`, `DEMO_USER_PASSWORD` |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `DATABASE_URL` |
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_PORT`, `QDRANT_GRPC_PORT`, `QDRANT_DOCUMENTS_COLLECTION` |
| OpenAI and RAG | `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_DIMENSIONS`, `RAG_SCORE_THRESHOLD`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MAX_ANSWER_TOKENS` |
| Ingestion | `MAX_UPLOAD_SIZE_MB`, `CHUNK_SIZE`, `CHUNK_OVERLAP` |
| Conversations | `CHAT_HISTORY_MESSAGE_LIMIT` |
| Reranking and evaluation | `RERANKER_MODEL`, `RAGAS_LLM_MODEL`, `RAGAS_EMBEDDING_MODEL` |

Never place a real OpenAI key, cloud database password, Qdrant Cloud key, or production JWT secret
in `.env.example`.

## Docker and Health

PostgreSQL listens on `5432` and Qdrant on `6333` by default. Docker named volumes preserve local
data. Check both dependencies through the application:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Stop services without deleting data:

```powershell
docker compose down
```

Use `docker compose down --volumes` only when intentionally resetting local demo data.

## Authentication

`python -m scripts.seed_demo` idempotently creates or refreshes these accounts:

| Email | Role |
| --- | --- |
| `developer@demo.com` | Developer |
| `hr@demo.com` | HR |
| `finance@demo.com` | Finance |
| `executive@demo.com` | Executive |

All demo users receive `DEMO_USER_PASSWORD`. The example value `ekip_demo_password` is local-demo
only. JWTs are stored in browser `sessionStorage`, so a login survives normal page refreshes and is
cleared by logout or the end of the browser session. Identity and role always come from the
validated JWT and database user, never from frontend request fields.

## Document Ingestion

Open `/documents`, select a PDF, DOCX, PPTX, or Markdown file, and choose one or more allowed roles.
The backend validates the extension, media type, size, and content hash; writes only a temporary
file; parses and chunks it with Docling; creates OpenAI `text-embedding-3-small` vectors and
FastEmbed sparse vectors; and indexes named `dense` and `sparse` vectors in Qdrant. PostgreSQL
tracks `PROCESSING`, `READY`, or `FAILED`, chunk count, uploader, roles, and safe error details.
Temporary upload files are deleted after processing. Deletion is uploader-only and removes the
document's Qdrant points.

The first parsing run may download Docling model assets into the ignored local model cache. HTML,
CSV, and Excel remain intentionally out of scope because the four required formats cover the MVP
without widening upload validation and parser testing.

## RBAC Retrieval

Each Qdrant point carries `allowed_roles` plus document and chunk metadata. The backend resolves the
authenticated role and includes an `allowed_roles` filter in every dense and sparse prefetch. The
filter runs before fusion, reranking, context selection, and citation creation, preventing
restricted chunks from entering any downstream candidate pool. Filtering after retrieval would be
both less secure and lower quality.

## Query Intelligence and Retrieval

Query Intelligence classifies FAQ, specific search, multi-document comparison, summarization, and
restricted-data questions, then chooses a centralized profile:

| Profile | Executed strategy | Candidate behavior |
| --- | --- | --- |
| FAST | `DENSE` | Dense Top-K 3 |
| BALANCED | `HYBRID_RRF` | Dense + sparse Qdrant RRF, Top-K 8 |
| ACCURATE | `HYBRID_RRF_RERANK` | Hybrid Top-K 15, BGE rerank, final Top-K 5 |

Hybrid retrieval combines semantic similarity with exact-term matching. RRF merges dense and sparse
ranks without relying on incomparable raw score scales. The cross-encoder is reserved for ACCURATE
queries because it improves final ordering at a meaningful latency cost. The first ACCURATE query
downloads the configured BGE model into an ignored local cache and later requests reuse the same
process-wide instance.

## Chat, Conversations, and Citations

Open `/chat` to ask questions against documents authorized for the signed-in role. `POST
/api/chat/stream` emits `metadata`, incremental `token` events, `citations`, and `complete`; failures
after streaming begins emit a safe `error` event. Citations are created only from final chunks
actually supplied to generation and include the filename, page/section when available, and snippet.

Conversations and messages persist in PostgreSQL and are always owner-scoped. Citation snapshots
remain attached when a conversation is reopened. Recent messages may help conversational answer
generation but never become authoritative document evidence. The browser uses `fetch` with a
`ReadableStream` because streaming is an authenticated `POST`, not an unauthenticated native
`EventSource` request.

## Retrieval Inspector

Open `/inspector` for user-scoped query explainability. Each query records classification, profile,
actual strategy, fallback status, retrieval latency, candidates, ranks, available dense/RRF/reranker
scores, and final-context inclusion. Candidate metadata and bounded snippets are copied into
PostgreSQL, so historical inspection still works after source document deletion. Missing and
other-user query IDs return the same safe not-found response.

## RAGAS Evaluation

`python -m scripts.seed_evaluation_data` idempotently indexes five synthetic Markdown policies with
their intended roles. The checked-in `evaluation/dataset.json` contains 23 matching synthetic
cases. Open `/evaluations` to run the representative five cases or the full dataset explicitly.
Normal chat requests never invoke RAGAS.

Each evaluation uses the existing authenticated retrieval and generation path without creating a
conversation. RAGAS scores Faithfulness, Answer Relevancy, Context Precision, and Context Recall;
runs, progress, nullable metric failures, case results, and Inspector query IDs persist in
PostgreSQL. Explicit runs keep normal query latency and API cost predictable.

## Optimization Recommendations

Completed runs are evaluated against fixed rules:

```text
Context Recall < 0.65
Context Precision < 0.60
Retrieval Latency > 2500 ms
```

Recommendations reflect the executed profile and strategy, persist with `OPEN` or `DISMISSED`
status, and never change Top-K, profiles, Qdrant, environment variables, or deployment. A human
reviews the evidence and decides whether to act; the system does not perform automatic RAG tuning.

Regenerate guidance for an existing completed run with:

```powershell
cd backend
python -m scripts.generate_recommendations <evaluation-run-uuid>
```

## Analytics

Open `/analytics` for aggregate, non-sensitive system behavior. One authenticated endpoint,
`GET /api/analytics/summary`, returns:

- total queries and average retrieval latency
- the latest completed evaluation's four quality averages
- executed retrieval-strategy counts
- up to 100 recent latency points
- up to 20 completed evaluation-run aggregates
- up to 20 persisted open recommendations

ECharts renders strategy distribution, evaluation history, and latency over time. Null metrics are
shown as `N/A` or chart gaps rather than zeros. Analytics never includes raw queries, conversation
content, document snippets, or another user's detailed Inspector data.

## API Surface

```text
POST   /api/auth/login
GET    /api/auth/me
POST   /api/documents
GET    /api/documents
GET    /api/documents/{document_id}
DELETE /api/documents/{document_id}
POST   /api/conversations
GET    /api/conversations
GET    /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}
POST   /api/chat
POST   /api/chat/stream
GET    /api/queries
GET    /api/queries/{query_id}
GET    /api/queries/{query_id}/retrieval
POST   /api/evaluations/run
GET    /api/evaluations
GET    /api/evaluations/{run_id}
GET    /api/recommendations
PATCH  /api/recommendations/{recommendation_id}
GET    /api/analytics/summary
```

FastAPI `/docs` is the authoritative interactive request/response reference.

## Database Migrations

Apply and verify the complete migration chain:

```powershell
cd backend
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Schema changes must use Alembic; no manual table edits are required. To create a future migration:

```powershell
python -m alembic revision --autogenerate -m "describe change"
```

## Validation

Backend:

```powershell
cd backend
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest
python -m pip check
python -m alembic check
```

Frontend:

```powershell
cd frontend
npm run format:check
npm run lint
npm run type-check
npm run test
npm run build
npm audit --omit=dev
```

Repository whitespace check:

```powershell
git diff --check
```

## Deployment Architecture

Phase 13 will deploy the same architecture without changing the application boundary:

```text
GitHub
  |-- Vercel: Vue 3 frontend
  |      |
  |      +-- REST / SSE to Render
  |
  +-- Render: FastAPI backend
         |-- Neon PostgreSQL
         |-- Qdrant Cloud
         +-- OpenAI API
```

Deployment has not been configured yet. The code is deployment-ready through environment-based
frontend/backend URLs, configurable CORS, PostgreSQL migrations, configurable Qdrant URL/API key,
configurable OpenAI models, temporary upload cleanup, and a successful production frontend build.
The BGE reranker's first model load is a Phase 13 resource consideration for Render; it is not a
reason to replace the working local reranker prematurely.
