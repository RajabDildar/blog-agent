# Blog Agent

A multi-stage AI blog writing agent built with Python and LangGraph. It researches a topic when necessary, creates an article plan, generates sections in parallel, reviews the complete article, performs a targeted revision when needed, and generates contextual images that are inserted into the appropriate sections.

The project is designed around a simple goal: generate a small number of high-quality technical blogs while relying on free or low-cost AI services.

## Features

* Research-aware blog generation
* Automatic decision on whether web research is needed
* Web research using Tavily
* Structured article planning
* Parallel section generation using LangGraph
* Separate LLM roles for routing, planning, writing, research, and editing
* Editorial review with a quality score
* Targeted section revision
* AI-generated images using Cloudflare Workers AI
* Image placement based on article sections
* Deterministic Markdown image insertion
* Structured outputs using Pydantic
* Rate limiting for Groq API usage
* Retry handling for Groq rate-limit errors
* Markdown validation before completion
* LangSmith tracing support

## Architecture

```text
                         ┌───────────────┐
                         │     Topic     │
                         └───────┬───────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │    Router     │
                         │    8B LLM     │
                         └───────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
               Research needed          No research
                    │                         │
                    ▼                         │
             ┌───────────────┐                │
             │    Tavily     │                │
             │    Research   │                │
             └───────┬───────┘                │
                     │                        │
                     └──────────┬─────────────┘
                                ▼
                         ┌───────────────┐
                         │    Planner    │
                         │     70B       │
                         └───────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                Section 1    Section 2    Section N
                  Worker       Worker       Worker
                    │            │            │
                    └────────────┼────────────┘
                                 ▼
                         ┌───────────────┐
                         │     Merge     │
                         │    Python     │
                         └───────┬───────┘
                                 ▼
                         ┌───────────────┐
                         │    Editor     │
                         │     70B       │
                         └───────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                 Approved                  Revision
                    │                         │
                    │                         ▼
                    │                  Targeted sections
                    │                         │
                    │                         ▼
                    │                       Merge
                    │                         │
                    └────────────┬────────────┘
                                 ▼
                         ┌───────────────┐
                         │ Image Planner │
                         │     8B        │
                         └───────┬───────┘
                                 ▼
                         ┌───────────────┐
                         │   Cloudflare  │
                         │   Workers AI  │
                         └───────┬───────┘
                                 ▼
                         ┌───────────────┐
                         │   Validator   │
                         │    Python     │
                         └───────┬───────┘
                                 ▼
                            Final Blog
```


## LLM Strategy

The project does not use the same model for every task.

The current model allocation is:

| Task               | Model                     |
| ------------------ | ------------------------- |
| Routing            | `llama-3.1-8b-instant`    |
| Research synthesis | `llama-3.1-8b-instant`    |
| Article planning   | `llama-3.3-70b-versatile` |
| Section writing    | `llama-3.3-70b-versatile` |
| Editorial review   | `llama-3.3-70b-versatile` |
| Revision           | `llama-3.3-70b-versatile` |
| Image planning     | `llama-3.3-70b-versatile` |

The smaller model handles relatively simple classification and research processing, while the larger model is reserved for tasks that directly affect article quality.

## Image Generation

Images are planned separately from article generation.

The image planner determines:

* Which sections need an image
* What type of image is appropriate
* Why the image is useful
* Where the image should appear
* Alt text
* Caption

Python then generates the final image prompt and filename.

This avoids allowing an LLM to directly modify the article Markdown.

For example:

```text
Image Planner
    |
    | section_id = 3
    | placement = middle
    |
    v
Python Markdown Processor
    |
    v
Section 3
    |
    v
Image inserted at the requested position
```

Images are generated using Cloudflare Workers AI and stored in the `images/` directory.

## Project Structure

```text
blog-agent/
├── config/
│   └── settings.py
│
├── eval/
│   ├── topics.json
│   ├── README.md
│   └── runs/
│
├── generated_blogs/
│
├── graph/
│   └── main_graph.py
│
├── images/
│
├── nodes/
│   ├── editor.py
│   ├── image_generator.py
│   ├── image_planner.py
│   ├── merger.py
│   ├── orchestrator.py
│   ├── research.py
│   ├── revision.py
│   ├── router.py
│   ├── validator.py
│   └── worker.py
│
├── prompts/
│   ├── editor.py
│   ├── image.py
│   ├── planner.py
│   ├── research.py
│   ├── revision.py
│   ├── router.py
│   └── writer.py
│
├── schemas/
│   ├── models.py
│   └── state.py
│
├── services/
│   ├── cloudflare.py
│   ├── image_prompt.py
│   ├── llm.py
│   ├── markdown.py
│   ├── run_metrics.py
│   ├── storage.py
│   └── tavily.py
│
├── .env.example
├── .gitignore
├── LICENSE
├── main.py
├── pyproject.toml
└── uv.lock
```

## Requirements

* Python 3.11+
* `uv`
* Groq API key
* Tavily API key
* Cloudflare account with Workers AI access

LangSmith is optional and can be enabled for tracing and debugging.

## Installation

Clone the repository:

```bash
git clone https://github.com/RajabDildar/blog-agent.git
cd blog-agent
```

Install dependencies with `uv`:

```bash
uv sync
```

Create the environment file:

```bash
cp .env.example .env
```

Add your API credentials to `.env`.

Example:

```env
GROQ_API_KEY=

GROQ_WRITER_MODEL=llama-3.3-70b-versatile
GROQ_ROUTER_MODEL=llama-3.1-8b-instant
GROQ_RESEARCH_MODEL=llama-3.1-8b-instant
GROQ_PLANNER_MODEL=llama-3.3-70b-versatile
GROQ_EDITOR_MODEL=llama-3.3-70b-versatile
GROQ_REVISION_MODEL=llama-3.3-70b-versatile

TAVILY_API_KEY=

CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=

CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
```

Optional LangSmith configuration:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=blog-agent
```

## Usage

Start the agent with:

```bash
uv run python main.py
```

Enter a topic when prompted:

```text
Enter blog topic: AI in finance
```

The agent will then run the complete generation pipeline.

Generated Markdown files are saved in:

```text
generated_blogs/
```

Generated images are saved in:

```text
images/
```

## Research

The router determines whether research is necessary.

There are three modes:

### Closed Book

Used for evergreen topics where external research does not materially improve the article.

### Hybrid

Used when the topic is primarily evergreen but current information, examples, products, statistics, or recent developments would improve the article.

### Open Book

Used when the article depends heavily on current information.

When research is performed, Tavily results are collected and converted into structured evidence before being passed to the planning and writing stages.

The writing nodes are instructed not to invent sources or URLs.

## Article Generation

The planner creates a structured article plan containing:

* Article title
* Thesis
* Opening angle
* Reader promise
* Target audience
* Tone
* Article type
* Key takeaways
* Section structure
* Section goals
* Section requirements
* Research requirements
* Citation requirements
* Code requirements

Each section is then generated independently.

LangGraph fans these section-generation tasks out so they can run independently and then merges them back into the correct article order.

## Editorial Review

After all sections are generated, the complete article is reviewed by an editor model.

The editor checks:

* Technical accuracy
* Unsupported claims
* Repetition
* Coherence
* Structure
* Citations
* Code
* Usefulness
* Introduction
* Conclusion

The review produces a score from 1 to 10.

If the article does not meet the required quality threshold, only the affected sections are revised.

The project currently limits this revision cycle to one pass to avoid unnecessary API usage.

## API Usage Strategy

The project is designed to work within free API limits.

Instead of using the most expensive model for every operation, model usage is divided according to task complexity.

The architecture also uses rate limiting and retry handling for Groq requests.

The goal is not to generate large numbers of articles. The goal is to use a limited number of API calls to produce a small number of substantially better articles.

## Evaluation

The `eval/` directory contains topics used to evaluate the generated articles.

Articles can be manually evaluated using:

* Overall quality
* Structure
* Technical accuracy
* Research quality
* Coherence
* Usefulness
* Writing quality
* Citations
* Image quality

Generation metrics can also be recorded, including:

* Generation time
* Number of LLM calls
* Number of research calls
* Number of image calls
* Revision count

The evaluation process is intended to compare changes to prompts, models, research strategy, and graph architecture rather than relying only on subjective impressions from a single generated article.

## Design Principles

### LLMs make decisions, Python enforces structure

The project intentionally avoids using an LLM for operations that can be handled deterministically.

For example:

* LLM decides where an image belongs.

* Python inserts the image.

* LLM decides the article structure.

* Python preserves section ordering.

* LLM identifies sections requiring revision.

* Python replaces those sections.

This reduces unnecessary model work and makes the output more predictable.

### Structured outputs

Important LLM operations use Pydantic schemas instead of relying on free-form text.

This includes:

* Routing
* Planning
* Research evidence
* Section generation
* Editorial review
* Image planning

### Bounded agent behavior

The agent does not continuously loop until it believes the article is perfect.

The current pipeline uses bounded steps:

```text
Research
   ↓
Plan
   ↓
Generate
   ↓
Review
   ↓
One targeted revision
   ↓
Images
   ↓
Validation
```

This keeps API usage predictable.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
