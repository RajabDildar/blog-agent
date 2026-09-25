# Blog Agent

A Python-based technical blog generation workflow built with LangGraph, LangChain, Groq, Gemini, Tavily, and Cloudflare Workers AI.

The agent validates user requests via an Intent Gateway, supports human-in-the-loop clarification for vague topics, decides whether research is needed via a research router, plans the article, generates sections in parallel, reviews and revises the content, validates Markdown, plans and generates images, validates the final artifact, and saves the result only after the final checks pass.

Graph execution is checkpointed, so a run that fails partway through — a provider outage, a node error, or even the process being killed — can be resumed from the last completed step instead of starting over.

## What it does

- Validates user input safety, technical scope, and specificity via the Intent Gateway.
- Supports LangGraph human-in-the-loop clarification for vague topics.
- Routes topics between closed-book and research-backed generation.
- Uses Tavily for web research when required.
- Creates a structured article plan with ordered sections.
- Generates section bodies in parallel with LangGraph `Send`.
- Appends an application-owned `## Sources` section for research-backed articles.
- Validates Markdown structure and repairs formatting deterministically or with LLM assistance.
- Verifies inline citations and final Sources deterministically.
- Reviews the assembled article with a holistic editor and revises selected sections.
- Enforces a deterministic citation release gate that blocks publication on unresolved high-severity citation defects.
- Enforces deterministic H1/H2 ownership in Python.
- Parses Markdown with `markdown-it-py` instead of relying on regex for document structure.
- Formats Markdown with `mdformat` and validates it again afterward.
- Plans up to three article-specific images.
- Generates images with Cloudflare Workers AI and inserts them into the planned sections.
- Stages generated images per run to prevent cross-run contamination.
- Performs a final Markdown and image integrity check before publishing.
- Records per-run diagnostics, including stages, provider attempts, retries, repairs, revisions, image attempts, and failures.
- Persists graph state after every super-step so an in-progress run survives a node failure or process termination.
- Resumes a failed or interrupted run by `run_id` without repeating already-completed work where LangGraph's checkpoint semantics make that possible.
- Exposes a FastAPI HTTP backend with Google authentication, opaque session cookies, CSRF protection, and PostgreSQL-backed application state.

## Workflow

```text
START
  |
  v
Intent Gateway
  |
  +------ blocked / invalid -------> END
  |
  | (safe input)
  |
  +-- clear --+-- vague -----------> interrupt()
  |            |                          |
  |            |                   clarification
  |            |                   user selects
  |            |                   resume(run_id, human_response=...)
  |            |                          |
  |            +----------+---------------+
  |                       |
  |                finalized topic
  |
  v
Router
  |
  +---- Research ----+
  |                  |
  +------------------+
           |
           v
      Orchestrator
           |
           v
    Parallel Workers
           |
           v
     Merge + Sources
           |
           v
   Article Validation
           |
       +---+---+
       |       |
     Valid   Invalid
       |       |
       |     Repair
       |       |
       +---<---+
           |
           v
   Citation Verifier
           |
           v
        Editor (Pass 1)
           |
      +----+----+
      |         |
   Approved   Revise
      |         |
      |      Revision
      |         |
      |    Merge + Sources
      |         |
      |  Article Validation
      |         |
      |  Citation Verifier (Pass 2)
      |         |
      +----+----+
           |
           v
 Citation Release Gate
       +---+---+
       |       |
     Pass    Fail
       |       |
       v       v
 Image Planner Stop
       |
       v
 Image Generator
       |
       v
 Final Validation
       |
   +---+---+
   |       |
 Valid   Invalid
   |       |
   v       v
  Save    Stop
   |
   v
  END
```

Two validation boundaries are intentional.

**Article validation** checks the article before image generation.

**Final validation** checks the completed Markdown and generated image artifacts before publication.

LangGraph checkpoints state at every super-step boundary along this path, so a failure at any node leaves the preceding, successfully-completed nodes durable and available on resume.

## Project structure

```text
blog-agent/
├── apps/
│   └── api/                       # Phase 3: FastAPI backend application
│       ├── __init__.py
│       ├── main.py                # FastAPI app factory and router registration
│       ├── config.py              # Pydantic BaseSettings (env / .env)
│       ├── dependencies.py        # FastAPI dependencies: DB, auth, CSRF, anon
│       ├── auth/
│       │   ├── google.py          # Google Identity Services ID token verification
│       │   ├── sessions.py        # Opaque session tokens with SHA-256 DB storage
│       │   └── csrf.py            # Double-submit-cookie CSRF + Origin validation
│       ├── db/
│       │   ├── base.py            # SQLAlchemy DeclarativeBase
│       │   ├── models.py          # User, Session, Run ORM models + enums
│       │   ├── session.py         # Pooled engine and get_db generator
│       │   └── migrations/        # Alembic (application tables only)
│       ├── routers/
│       │   ├── auth.py            # POST /auth/google, POST /auth/logout, GET /auth/me
│       │   ├── runs.py            # POST /runs, GET /runs, GET/PATCH /runs/{id}/...
│       │   └── gallery.py         # GET /gallery, GET /featured
│       ├── schemas/
│       │   ├── auth.py            # GoogleAuthRequest, UserResponse
│       │   └── runs.py            # RunCreateRequest, RunResponse, GalleryItemResponse, …
│       └── services/
│           ├── run_service.py     # Run CRUD with strict ownership / invariant enforcement
│           └── claim_service.py   # Anonymous run transfer on Google login
├── blog_agent/
│   ├── __init__.py                # public API: run(), resume()
│   ├── config/
│   │   └── settings.py
│   ├── graph/
│   │   └── main_graph.py
│   ├── nodes/
│   │   ├── intent_gateway.py      # Phase 2: first node; safety, scope, HITL
│   │   └── ...                    # router, research, orchestrator, workers, …
│   ├── prompts/
│   │   ├── intent_gateway.py      # Phase 2: intent analysis prompts
│   │   └── ...                    # router, editor, writer, …
│   ├── schemas/
│   │   ├── context.py
│   │   ├── models.py              # IntentAnalysis, IntentHumanResponse, …
│   │   └── state.py               # State with intent/HITL fields
│   └── services/
│       ├── intent_analysis.py     # Phase 2: Gemini → Groq intent service
│       └── ...                    # article_structure, checkpointer, citation, …
├── eval/
├── generated_blogs/
├── images/
├── tests/
├── alembic.ini
├── docker-compose.yml             # Phase 3: local PostgreSQL container
├── .env.example
├── .gitignore
├── LICENSE
├── main.py
├── pyproject.toml
└── uv.lock
```

## Technology

| Area | Technology |
|---|---|
| Language | Python 3.14+ |
| Workflow | LangGraph |
| LLM framework | LangChain |
| Writing and revision | Groq |
| Routing, planning, research processing, editing | Gemini |
| Intent analysis (primary) | Gemini |
| Intent analysis (fallback) | Groq |
| Web research | Tavily |
| Image generation | Cloudflare Workers AI |
| Structured data | Pydantic |
| Markdown parsing | markdown-it-py |
| Markdown formatting | mdformat + GFM |
| Graph persistence | LangGraph checkpointing (`langgraph-checkpoint-sqlite`) |
| HTTP backend | FastAPI |
| Application database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Authentication | Google Identity Services |
| Package management | uv |
| Testing | pytest |

## Models and providers

Model names are configured through environment variables in `blog_agent/config/settings.py`.

The current workflow uses:

- Gemini as the primary intent analysis model (safety, scope, clarification classification).
- Groq as the intent analysis fallback model; also used for section writing and revision/repair.
- Gemini for routing, research extraction, article planning, editorial review, and image planning.
- Tavily for web search.
- Cloudflare Workers AI for image generation.

The repository's `.env.example` contains the current environment variable names and model settings.

## Setup

Clone the repository:

```bash
git clone https://github.com/RajabDildar/blog-agent.git
cd blog-agent
```

Install the project and development dependencies:

```bash
uv sync
```

Create the environment file:

```bash
cp .env.example .env
```

Fill in the API credentials in `.env`.

Required credentials for the article generation pipeline:

```env
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

Required for the FastAPI backend (Phase 3+):

```env
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/blog_agent
TEST_DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/blog_agent_test
GOOGLE_CLIENT_ID=your_google_oauth_client_id
SESSION_SECRET_KEY=a_long_random_string
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
ENVIRONMENT=development
```

Optional configuration:

```env
CHECKPOINT_SQLITE_PATH=runs/checkpoints.sqlite
SESSION_MAX_AGE_SECONDS=604800
```

`CHECKPOINT_SQLITE_PATH` controls where the LangGraph SQLite checkpoint database is created. It defaults to `runs/checkpoints.sqlite` if unset.

Never commit `.env` or real API credentials.

### Starting the local PostgreSQL database

A `docker-compose.yml` is provided for local development:

```bash
docker compose up -d
```

Apply the application Alembic migrations (application tables only — LangGraph checkpoint tables are managed separately by LangGraph):

```bash
uv run alembic upgrade head
```

### Starting the FastAPI backend

```bash
uv run uvicorn apps.api.main:app --reload
```

The API will be available at `http://localhost:8000`. The health endpoint is at `GET /healthz`.

## Run (CLI)

Start a new article generation run from the local CLI:

```bash
uv run python3 main.py
```

Enter your article request when prompted:

```text
Enter blog topic: AI agents in production
```

The run ID is printed immediately after it is generated:

```text
Run ID: 3f9a2c1e4b7d4a9f8c2e1a6b5d3f0c9a
```

The Intent Gateway evaluates the request before generation begins:

- **Clear, safe input** — the topic is finalized immediately and the existing generation pipeline starts.
- **Vague input** — the CLI presents a clarification question with three options. Select one or type a custom response; the graph resumes with the refined topic.
- **Still-vague after clarification** — the system proposes a concrete topic and asks for Proceed or Cancel confirmation.
- **Blocked input** — the request is rejected with a brief explanation and alternative topic suggestions.
- **Invalid / out-of-scope input** — the request is rejected with a message asking for a technical article topic.
- **Intent analysis unavailable** — if both Gemini and Groq intent providers fail, generation is aborted rather than bypassing safety.

A successful run reports the generated title, revision count, image counts, output path, and run diagnostics path.

### Resuming a failed run

If a run fails — a provider error, a validation failure that can't self-heal, or the process being killed — it can be resumed from its last durable checkpoint using the printed run ID:

```bash
uv run python3 main.py --resume 3f9a2c1e4b7d4a9f8c2e1a6b5d3f0c9a
```

Resume behavior:

- The graph continues from the last completed super-step; nodes that already produced output are not re-executed where LangGraph's pending-write semantics allow it.
- The original topic is not re-submitted; LangGraph replays from its own persisted state.
- A run that already completed successfully cannot be resumed.
- An unknown run ID cannot be resumed.
- Run diagnostics are continued, not overwritten — the original `run_id` and start time are preserved, and a `run_resumed` event is appended to the existing event history.

`run()` never resumes an existing thread implicitly. Supplying a `run_id` that is already in use raises an error instructing you to use `resume()` instead.

`resume(run_id, human_response=...)` is used to deliver a clarification or confirmation response to a graph that is waiting at a LangGraph HITL interrupt.

## FastAPI Backend (Phase 3)

The `apps/api` package provides the HTTP backend for Blog Agent v3.

### Authentication

Authentication uses Google Identity Services. The frontend sends a Google credential JWT to `POST /auth/google`. The backend verifies signature, audience, issuer, and expiry using Google's public certificates. The raw Google access token is never stored.

On successful authentication:
- A cryptographically random opaque session token is generated.
- Only its SHA-256 hash is stored in the `sessions` PostgreSQL table.
- The raw token is sent as an `HttpOnly`, `SameSite=Lax` cookie named `blog_session`.
- A non-HttpOnly CSRF cookie named `blog_csrf` is issued for the double-submit-cookie CSRF pattern.
- Any anonymous runs from the visitor's browser are transferred to the newly-authenticated user account.

### CSRF Protection

All cookie-authenticated state-changing requests (`POST`, `PATCH`, etc.) must supply:

- The `blog_csrf` cookie value (set automatically by the browser).
- The same value in the `X-CSRF-Token` request header (set by the frontend SPA).
- A valid `Origin` or `Referer` header matching `ALLOWED_ORIGINS`.

Tokens are compared with `hmac.compare_digest` to avoid timing attacks.

### Anonymous visitors

Visitors who have not signed in receive an opaque `blog_anon` cookie (`HttpOnly`, `SameSite=Lax`). This cookie identifies anonymous run ownership. It does not encode any user data.

### Application data model

| Table | Purpose |
|---|---|
| `users` | Authenticated users identified by Google `sub` |
| `sessions` | Hashed opaque session tokens with expiry |
| `runs` | Article generation requests, status, visibility, and outcomes |

Alembic manages only these application tables. LangGraph checkpoint tables are managed exclusively by LangGraph.

Run status vocabulary (exact):

```text
queued | running | awaiting_input | paused | completed |
failed | blocked | invalid | cancelled | expired
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/google` | Authenticate with Google ID token |
| `POST` | `/auth/logout` | Revoke session and clear cookies |
| `GET` | `/auth/me` | Return authenticated user profile |
| `POST` | `/runs` | Create a new queued article generation run |
| `GET` | `/runs` | List runs owned by the current user/session |
| `GET` | `/runs/{id}` | Fetch a run by ID (owner or public completed only) |
| `PATCH` | `/runs/{id}/visibility` | Change visibility (completed runs only) |
| `PATCH` | `/runs/{id}/feature` | Admin-only: feature a public completed article |
| `POST` | `/runs/{id}/input` | Submit clarification/confirmation input (Phase 4) |
| `POST` | `/runs/{id}/resume` | Resume a failed/paused run (Phase 4) |
| `GET` | `/runs/{id}/events` | SSE event stream for generation progress (Phase 4) |
| `GET` | `/gallery` | Public gallery of completed articles |
| `GET` | `/featured` | Admin-curated featured articles |
| `GET` | `/healthz` | Health check |

Long-running generation never executes inside request handlers. Phase 4 adds the RQ worker backend that executes `blog_agent.run()` out-of-process.

### Ownership rules

- Authenticated users can access only their own private runs.
- Anonymous visitors can access only runs tied to their `blog_anon` cookie and not expired.
- Public completed runs are readable by anyone via gallery/article endpoints.
- Admin status does **not** grant broad read access to arbitrary private user content.
- Only administrators can feature articles, and only when the run is already `visibility=public` and `status=completed`.
- No public admin bootstrap endpoint exists. Admin status is granted manually in PostgreSQL.

## Output (CLI)

Generated Markdown articles are saved under:

```text
generated_blogs/
```

Published generated images are stored under article/run-specific directories:

```text
images/<article>/<run_id>/
```

Each execution also gets a private staging directory:

```text
runs/<run_id>/images/
```

Run diagnostics are written to:

```text
runs/<run_id>/diagnostics.json
```

The LangGraph checkpoint database is written to:

```text
runs/checkpoints.sqlite
```

(or the path set by `CHECKPOINT_SQLITE_PATH`.)

The `runs/` directory is ignored by Git.

## Reliability and validation

The workflow is designed so invalid artifacts do not silently reach the output directory.

### Markdown

Python owns the article H1 and planned H2 structure. Workers return section body Markdown only.

The Markdown layer:

1. parses Markdown structurally with `markdown-it-py`
2. validates the document
3. applies deterministic repairs where safe
4. uses LLM repair only when needed
5. validates the repaired result
6. formats valid Markdown
7. validates the formatted result again
Code blocks are treated as code rather than article structure.

### Images

Generated images are isolated by `run_id`.

Before publication, the system checks that:

- every generated image was inserted
- each generated image is referenced exactly once
- generated paths are unique
- staged images exist and are non-empty
- published paths match the paths embedded in Markdown
- unrelated local image references exist
- failed image generation does not get silently ignored
### Publication

The final Markdown is written only after final validation succeeds.

Image publication is validated before the Markdown replacement, and the storage layer cleans up newly published images if a later publication step fails.

### Provider failures

LLM model-level retries are disabled. LangGraph owns provider retries through a shared retry policy.

Transient provider failures such as rate limits, timeouts, connection failures, and applicable server errors can be retried. Permanent request or validation errors are not treated as transient.

Cloudflare image generation uses its own small retry policy for transient image-provider failures and avoids retrying permanent request/configuration errors.

### Graph persistence and recovery

The compiled graph is checkpointed with a synchronous SQLite-backed LangGraph saver (`services/checkpointer.py`). Checkpoints are written at every graph super-step boundary, keyed by `thread_id`, using the application `run_id` as the thread identity.

This means:

- A node failure, a provider outage, or a killed process leaves all prior, successfully-completed steps durable.
- `resume(run_id)` picks up from the latest checkpoint instead of restarting the graph.
- External side effects (LLM calls, Tavily calls, image generation) are **not** made transactional by checkpointing — a node may repeat its side effect after a resume. Publication writes remain atomic and safe to repeat regardless.
- The graph itself is unaware of whether it is running for the first time or resuming; only `run()` and `resume()` differ in how they invoke it.

## Run diagnostics

Every run has a unique `run_id`.

Diagnostics record information such as:

```text
current stage
current provider
provider attempts
retry count
Markdown repairs
editorial reviews
editorial revisions
image attempts
final validation failures
failure type and message
```

This makes failed executions inspectable without putting diagnostic data into the graph state. Diagnostics are stored separately from LangGraph's checkpoint state and survive a resume: prior events, start time, and retry counts are preserved, and new events are appended rather than overwriting history.

## Testing

Run the complete test suite:

```bash
uv run pytest
```

The tests cover the main reliability boundaries, including:

- Intent analysis: Gemini primary, Groq fallback, and double-provider failure
- Intent gateway: deterministic pre-validation, safety blocking, scope rejection, nonsense rejection
- LangGraph HITL interrupt and resume for clarification and confirmation flows
- Safety classification: contextual acceptance and blocking across sensitive topics
- Public package API isolation (`run`, `resume`)
- Markdown parsing and validation
- section validation
- deterministic and LLM Markdown repair
- Markdown quality-gate behavior
- image insertion
- final image validation
- run-isolated image generation
- filesystem publication
- partial publication cleanup
- provider retry classification
- LangGraph retry behavior
- provider exception preservation
- run diagnostics (including intent event tracking)
- checkpointer creation and lifecycle
- `run()` / `resume()` contract semantics
- resume recovery for worker, editor, article-repair, and image-generation failures
- resume recovery after real process termination (subprocess kill and restart)
- diagnostics continuity across a resume
- FastAPI application startup and health check
- Google ID token verification (mocked)
- Opaque session lifecycle: creation, lookup, expiry, revocation
- CSRF double-submit-cookie validation and Origin checking
- Run service ownership, visibility, and featured invariants
- Anonymous run claiming on Google login
- Authorization: private run isolation, admin-only feature operations

**437 tests pass** across 53 test modules as of Phase 3.

## Development principles

The project intentionally keeps the workflow small and explicit.

- Let Python own deterministic structure.
- Let the LLM handle generation and judgment.
- Parse Markdown instead of guessing document structure from strings.
- Validate after transformations.
- Separate content failures from provider, filesystem, and programming failures.
- Keep side effects behind validation boundaries.
- Preserve original provider exceptions so retry policy can classify them.
- Prefer focused tests around failure cases rather than relying only on successful generated articles.
- Avoid adding orchestration or abstractions unless the current workflow proves they are needed.
- Keep application identity and LangGraph thread identity aligned (`run_id == thread_id`) rather than introducing a separate mapping layer.
- Never run long-running generation inside FastAPI request handlers.
- Never store raw session tokens in the database; store only their SHA-256 hash.

## Evaluation

The `eval/` directory contains the current evaluation topics and supporting files.

Generated articles in `generated_blogs/` can be reviewed as concrete workflow outputs, while the test suite provides the main regression protection for Markdown and artifact correctness.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
