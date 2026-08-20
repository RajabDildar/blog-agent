# Blog Agent
 
A Python-based technical blog generation workflow built with LangGraph, LangChain, Groq, Gemini, Tavily, and Cloudflare Workers AI.
 
The agent takes a topic, decides whether research is needed, plans the article, generates sections in parallel, reviews and revises the content, validates Markdown, plans and generates images, validates the final artifact, and saves the result only after the final checks pass.
 
Graph execution is checkpointed, so a run that fails partway through — a provider outage, a node error, or even the process being killed — can be resumed from the last completed step instead of starting over.
 
## What it does
 
- Routes topics between closed-book and research-backed generation.
- Uses Tavily for web research when required.
- Creates a structured article plan with ordered sections.
- Generates section bodies in parallel with LangGraph `Send`.
- Reviews the assembled article and revises selected sections.
- Enforces deterministic H1/H2 ownership in Python.
- Parses Markdown with `markdown-it-py` instead of relying on regex for document structure.
- Repairs Markdown deterministically first, then with an LLM when needed.
- Formats Markdown with `mdformat` and validates it again afterward.
- Plans up to three article-specific images.
- Generates images with Cloudflare Workers AI and inserts them into the planned sections.
- Stages generated images per run to prevent cross-run contamination.
- Performs a final Markdown and image integrity check before publishing.
- Records per-run diagnostics, including stages, provider attempts, retries, repairs, revisions, image attempts, and failures.
- Persists graph state after every super-step so an in-progress run survives a node failure or process termination.
- Resumes a failed or interrupted run by `run_id` without repeating already-completed work where LangGraph's checkpoint semantics make that possible.
## Workflow
 
```text
START
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
         Merge
           |
           v
        Editor
           |
      +----+----+
      |         |
   Approved   Revise
      |         |
      |      Revision
      |         |
      +----<----+
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
      Image Planner
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
├── config/
│   └── settings.py
├── eval/
│   ├── README.md
│   └── topics.json
├── generated_blogs/
├── graph/
│   └── main_graph.py
├── images/
├── nodes/
├── prompts/
├── schemas/
│   ├── models.py
│   ├── state.py
│   └── context.py
├── services/
│   ├── checkpointer.py
│   ├── cloudflare.py
│   ├── final_validation.py
│   ├── image_prompt.py
│   ├── llm.py
│   ├── markdown.py
│   ├── markdown_format.py
│   ├── markdown_llm_repair.py
│   ├── markdown_parser.py
│   ├── markdown_quality.py
│   ├── markdown_repair.py
│   ├── markdown_validation.py
│   ├── run_diagnostics.py
│   ├── run_paths.py
│   ├── section_validation.py
│   ├── storage.py
│   └── tavily.py
├── tests/
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
| Web research | Tavily |
| Image generation | Cloudflare Workers AI |
| Structured data | Pydantic |
| Markdown parsing | markdown-it-py |
| Markdown formatting | mdformat + GFM |
| Graph persistence | LangGraph checkpointing (`langgraph-checkpoint-sqlite`) |
| Tracing | LangSmith |
| Package management | uv |
| Testing | pytest |
 
## Models and providers
 
Model names are configured through environment variables in `config/settings.py`.
 
The current workflow uses:
 
- Groq for section writing and revision/repair.
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
 
Required credentials:
 
```env
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```
 
Optional configuration:
 
```env
CHECKPOINT_SQLITE_PATH=runs/checkpoints.sqlite
```
 
`CHECKPOINT_SQLITE_PATH` controls where the LangGraph SQLite checkpoint database is created. It defaults to `runs/checkpoints.sqlite` if unset.
 
Never commit `.env` or real API credentials.
 
## Run
 
Start a new run:
 
```bash
uv run python3 main.py
```
 
Enter a topic when prompted:
 
```text
Enter blog topic: AI agents in production
```
 
The run ID is printed immediately after it is generated:
 
```text
Run ID: 3f9a2c1e4b7d4a9f8c2e1a6b5d3f0c9a
```
 
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
 
## Output
 
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
- run diagnostics
- checkpointer creation and lifecycle
- `run()` / `resume()` contract semantics
- resume recovery for worker, editor, article-repair, and image-generation failures
- resume recovery after real process termination (subprocess kill and restart)
- diagnostics continuity across a resume
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
## Evaluation
 
The `eval/` directory contains the current evaluation topics and supporting files.
 
Generated articles in `generated_blogs/` can be reviewed as concrete workflow outputs, while the test suite provides the main regression protection for Markdown and artifact correctness.
 
## License
 
This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
 
