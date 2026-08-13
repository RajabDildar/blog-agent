# Blog Agent

A Python-based technical blog generation system built with LangGraph, LangChain, Groq, Gemini, Tavily, and Cloudflare Workers AI.

The project uses a structured multi-stage workflow to research a topic when needed, plan the article, generate sections in parallel, review and revise the content, validate the Markdown, generate relevant images, embed those images into the correct sections, and save the final article only after validation succeeds.

## Features

* Topic-aware routing between closed-book and research-backed generation.
* Web research through Tavily for current or externally grounded topics.
* Structured article planning with explicit sections, goals, word targets, and requirements.
* Parallel section generation using LangGraph `Send`.
* Editorial review with targeted section-level revision.
* Deterministic Markdown and section validation.
* Controlled repair flow for structural Markdown problems.
* LLM-assisted repair when deterministic fixes are insufficient.
* Image planning based on the actual article structure.
* Article-specific image descriptions and generation prompts.
* Cloudflare Workers AI image generation.
* Automatic image placement inside the corresponding article sections.
* Final artifact validation before saving.
* Generated blogs saved as Markdown files.
* LangSmith-compatible tracing for inspecting workflow execution.

## Architecture

The generation workflow is organized as a LangGraph state machine:

```text
START
  │
  ▼
Router
  │
  ├── Research ──────────────┐
  │                          │
  └──────────────────────────┤
                             ▼
                         Orchestrator
                             │
                             ▼
                       Parallel Workers
                             │
                             ▼
                           Merge
                             │
                             ▼
                          Editor
                             │
                 ┌───────────┴───────────┐
                 │                       │
             Approved              Revision needed
                 │                       │
                 │                       ▼
                 │                   Revision
                 │                       │
                 │                 Mark revision
                 │                       │
                 └───────────► Merge ◄───┘
                             │
                             ▼
                   Article Validation
                             │
                 ┌───────────┴───────────┐
                 │                       │
               Valid                  Invalid
                 │                       │
                 │                     Repair
                 │                       │
                 │               Validate again
                 │                       │
                 └───────────► Image Planner
                             │
                             ▼
                       Image Generator
                             │
                             ▼
                     Final Validation
                             │
                 ┌───────────┴───────────┐
                 │                       │
               Valid                  Invalid
                 │                       │
                 ▼                       ▼
               Save                    Stop
                 │
                 ▼
                END
```

There are two validation stages.

**Article validation** runs before image generation and checks the generated article structure.

**Final validation** runs after image generation and checks both the Markdown and image references.

This keeps content repair separate from image processing and prevents a broken final artifact from being written to disk.

## Project Structure

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
│   ├── article_validator.py
│   ├── editor.py
│   ├── image_generator.py
│   ├── image_planner.py
│   ├── merger.py
│   ├── orchestrator.py
│   ├── repair.py
│   ├── research.py
│   ├── revision.py
│   ├── router.py
│   ├── save.py
│   ├── validator.py
│   └── worker.py
├── prompts/
│   ├── editor.py
│   ├── image.py
│   ├── planner.py
│   ├── repair.py
│   ├── research.py
│   ├── revision.py
│   ├── router.py
│   └── writer.py
├── schemas/
│   ├── models.py
│   └── state.py
├── services/
│   ├── cloudflare.py
│   ├── final_validation.py
│   ├── image_prompt.py
│   ├── image_validation.py
│   ├── llm.py
│   ├── markdown.py
│   ├── markdown_repair.py
│   ├── markdown_validation.py
│   ├── run_metrics.py
│   ├── section_validation.py
│   ├── storage.py
│   └── tavily.py
├── tests/
├── .env.example
├── LICENSE
├── main.py
├── pyproject.toml
└── uv.lock
```

## Technology Stack

| Component                                       | Technology            |
| ----------------------------------------------- | --------------------- |
| Language                                        | Python 3.14+          |
| Workflow orchestration                          | LangGraph             |
| LLM framework                                   | LangChain             |
| Writing and revision                            | Groq                  |
| Planning, routing, editing, research processing | Google Gemini         |
| Web research                                    | Tavily                |
| Image generation                                | Cloudflare Workers AI |
| Validation                                      | Python + Pydantic     |
| Observability                                   | LangSmith             |
| Dependency management                           | uv                    |

## Models

The project separates model responsibilities rather than using a single model for every operation.

The current configuration supports:

* Groq model for section writing.
* Groq model for revisions and Markdown repair.
* Gemini model for routing, planning, editorial review, research extraction, and image planning.
* Cloudflare Workers AI for image generation.

Models are configured through environment variables in `config/settings.py`.

## Installation

The project uses `uv` for environment and dependency management.

Clone the repository and enter the project directory:

```bash
git clone https://github.com/RajabDildar/blog-agent.git
cd blog-agent
```

Create the environment and install dependencies:

```bash
uv sync
```

## Environment Variables

Create a `.env` file in the project root.

Use `.env.example` as the starting point:

```bash
cp .env.example .env
```

Configure the required API credentials.

Typical variables include:

```env
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key

CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

Optional model configuration can be set through:

```env
GROQ_WRITER_MODEL=llama-3.3-70b-versatile
GROQ_REVISION_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-3.1-flash-lite
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
```

Do not commit `.env` or API credentials.

## Running the Agent

Start the application with:

```bash
uv run python3 main.py
```

Enter a topic when prompted:

```text
Enter blog topic: AI Agents
```

After a successful run, the terminal reports the generated title, revision count, image count, validation repairs, and output path.

Generated articles are written to:

```text
generated_blogs/
```

Generated images are written to:

```text
images/
```

## Validation and Failure Handling

Validation is a hard requirement for successful generation.

The workflow does not save the article until the final artifact passes validation.

The article validation stage checks structural requirements such as:

* exactly one H1
* correct H2 section structure
* expected section order
* balanced Markdown code fences
* absence of unresolved generation markers

If structural validation fails, the workflow attempts a controlled repair. Deterministic fixes are preferred for problems that can be safely corrected in code. An LLM repair step is used for remaining structural problems.

After image generation, the final validator additionally checks that:

* generated images are actually referenced by the article
* image paths resolve to existing files
* planned images were successfully inserted

A failed final validation stops the workflow rather than saving an invalid article.

## Image Generation and Placement

Images are planned from the final article structure rather than generated independently of the content.

For each selected section, the image planner determines:

* the section that needs a visual
* the visual type
* why the image is useful
* what should appear in the image
* important visual elements
* placement within the section
* alt text
* caption

The application then builds a consistent generation prompt from that structured specification and sends it to Cloudflare Workers AI.

Images are inserted into the corresponding Markdown section using the planned placement.

The system also verifies that every generated image is actually embedded in the final article.

## Testing

Run the test suite with:

```bash
uv run pytest
```

The tests cover:

* article Markdown validation
* section-level validation
* image insertion
* final artifact validation
* heading and code-fence validation
* structural repair behavior

The test suite is intended to catch workflow regressions before generating new articles.

## Observability

The project can be traced with LangSmith.

Tracing is useful for inspecting:

* router decisions
* research queries and evidence
* article planning
* parallel section generation
* editorial feedback
* revision inputs and outputs
* image planning
* validation failures
* repair attempts
* final artifact generation

This is especially useful when a generated article does not match the expected workflow behavior.

## Evaluation

The `eval/` directory contains the beginnings of a repeatable evaluation workflow.

`eval/topics.json` contains test topics that can be used to compare generation behavior across changes to the workflow.

The purpose of evaluation is to compare actual generated artifacts instead of relying on a single successful example.

## Output

A successful run produces two types of artifacts.

### Blog

```text
generated_blogs/
└── ai_agents.md
```

### Images

```text
images/
├── 1_agent_architecture.png
├── 2_reasoning_loop.png
└── ...
```

The generated Markdown references the corresponding local image paths.

## Development Principles

The project intentionally favors a controlled workflow over adding more agents or unnecessary orchestration.

The main design principles are:

* Use structured outputs between workflow stages.
* Validate deterministic requirements in Python.
* Use LLMs for tasks that require judgment or generation.
* Fail explicitly when required operations fail.
* Do not silently skip failed image generation or insertion.
* Keep article repair separate from image processing.
* Save only after final validation succeeds.
* Keep the workflow understandable and testable.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for the full license text.
