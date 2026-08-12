# Blog Agent

A Python-based AI blog writing agent built with LangGraph, LangChain, Groq, Gemini, Tavily, and Cloudflare Workers AI.

The agent takes a blog topic, decides whether research is needed, gathers web evidence when necessary, creates a structured article plan, generates sections in parallel, reviews the complete article, performs a targeted revision when required, generates relevant images, inserts those images into the appropriate sections, validates the final Markdown, and saves the finished blog locally.

The project is designed to generate a small number of high-quality technical blogs while keeping API usage within free-tier limits.

## Features

* Topic-based blog generation
* Automatic research routing
* Closed-book, hybrid, and open-book research modes
* Web research using Tavily
* Structured research evidence using Pydantic
* Article planning with thesis, opening angle, reader promise, and key takeaways
* Parallel section generation with LangGraph `Send`
* Groq Llama 3.3 70B for section writing and revision
* Gemini for routing, research synthesis, planning, editing, and image planning
* Structured LLM outputs
* Editorial quality review
* Targeted revision of affected sections
* One bounded revision cycle
* Image planning based on article sections
* Image generation with Cloudflare Workers AI
* Deterministic image placement in Markdown
* Deterministic image filename generation
* Markdown validation
* Groq rate limiting and retry handling
* Optional LangSmith tracing
* Local Markdown and image output

## Architecture

The agent uses a graph-based workflow with a bounded review and revision loop.

```text
                         User Topic
                             |
                             v
                          Router
                         Gemini
                             |
             +---------------+---------------+
             |                               |
       No research                    Research required
             |                               |
             |                           Research
             |                           Tavily
             |                               |
             |                               v
             +--------------------------> Planner
                                           Gemini
                                             |
                                             v
                                  Parallel Section Workers
                                       Groq Llama 3.3 70B
                                             |
                                             v
                                            Merge
                                           Python
                                             |
                                             v
                                           Editor
                                           Gemini
                                             |
                              +--------------+--------------+
                              |                             |
                            Pass                         Revision
                              |                             |
                              |                   Affected sections only
                              |                             |
                              |                         Groq 70B
                              |                             |
                              |                          Merge again
                              |                             |
                              +--------------+--------------+
                                             |
                                             v
                                      Image Planner
                                          Gemini
                                             |
                                             v
                                      Image Generation
                                        Cloudflare
                                             |
                                             v
                                      Markdown Insertion
                                          Python
                                             |
                                             v
                                         Validator
                                          Python
                                             |
                                             v
                                        Save Blog
```

The system intentionally separates LLM decisions from deterministic operations.

For example:

* The LLM decides which section needs an image.

* Python inserts the image.

* The LLM decides which sections need revision.

* Python routes those sections to the revision node.

* The LLM creates the article structure.

* Python preserves section ordering.

## Model Strategy

Different models are used according to the task.

| Task               | Provider      | Model                             |
| ------------------ | ------------- | --------------------------------- |
| Routing            | Google Gemini | Configured Gemini model           |
| Research synthesis | Google Gemini | Configured Gemini model           |
| Article planning   | Google Gemini | Configured Gemini model           |
| Section writing    | Groq          | `llama-3.3-70b-versatile`         |
| Editorial review   | Google Gemini | Configured Gemini model           |
| Section revision   | Groq          | `llama-3.3-70b-versatile`         |
| Image planning     | Google Gemini | Configured Gemini model           |
| Image generation   | Cloudflare    | Configured Workers AI image model |

The larger Groq model is reserved for writing-related tasks. Gemini handles the larger-context structured-processing tasks such as research synthesis and editorial review.

## Research Routing

Before planning, the router determines whether external research is needed.

### Closed Book

Used for evergreen topics where current information does not materially improve the article.

```text
Topic
  |
  v
Router
  |
  v
closed_book
  |
  v
Planner
```

### Hybrid

Used for topics that are mostly evergreen but benefit from current tools, examples, products, statistics, releases, or other recent information.

```text
Topic
  |
  v
Router
  |
  v
hybrid
  |
  v
Tavily Research
  |
  v
Research Evidence
  |
  v
Planner
```

### Open Book

Used for topics that depend heavily on current information such as recent events, rankings, pricing, regulations, or recent releases.

```text
Topic
  |
  v
Router
  |
  v
open_book
  |
  v
Tavily Research
  |
  v
Research Evidence
  |
  v
Planner
```

The research stage converts search results into structured evidence containing claims, sources, supporting text, relevance, and optional publication dates.

## Article Planning

The planner produces a structured `Plan` containing:

* Blog title
* Thesis
* Opening angle
* Reader promise
* Audience
* Tone
* Blog type
* Constraints
* Key takeaways
* Section tasks

Each `Task` contains:

* Section ID
* Section title
* Goal
* Bullets
* Target word count
* Section role
* Tags
* Research requirement
* Citation requirement
* Code requirement
* Topics to avoid

The planner is instructed to create only the sections needed to explain the topic well rather than forcing a fixed section count.

## Parallel Section Generation

LangGraph uses `Send` to generate sections independently.

```text
                       Blog Plan
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          Worker 1      Worker 2      Worker 3
          Groq 70B      Groq 70B      Groq 70B
             |             |             |
             +-------------+-------------+
                           |
                           v
                         Merge
```

Each worker receives:

* Article thesis
* Reader promise
* Full outline
* Current task
* Previous section context
* Next section goal
* Relevant research evidence

This allows individual workers to write in parallel while reducing repetition between sections.

## Structured Section Output

Workers return structured `SectionOutput` objects rather than arbitrary text.

The output contains:

```text
task_id
markdown
summary
concepts_introduced
```

Generated sections are stored in a dictionary keyed by task ID.

LangGraph uses a dictionary reducer so multiple parallel workers can safely update the same state key.

## Editorial Review

After all sections are merged, the complete article is sent to an editorial review node.

The editor evaluates:

* Relevance
* Coherence
* Technical accuracy
* Unsupported claims
* Repetition
* Section structure
* Usefulness
* Code quality
* Citation quality
* Introduction
* Conclusion

The editor returns:

```text
Approval decision
Overall score
Issues
Sections requiring revision
```

An article is accepted when it meets the configured quality threshold and contains no high-severity issues.

## Targeted Revision

The system does not regenerate the entire article when problems are found.

Only affected sections are revised.

```text
Draft
  |
  v
Editor
  |
  +---- Pass ----------> Image planning
  |
  +---- Problems ------> Affected sections
                               |
                               v
                          Groq 70B
                               |
                               v
                            Merge
                               |
                               v
                            Editor
```

The revision cycle is intentionally limited to one pass to keep API usage bounded.

## Image Generation

Image planning happens after the article has passed through the editorial stage.

The image planner determines:

* Section ID
* Image type
* Purpose
* Placement
* Alt text
* Caption

Image types include:

* Technical diagrams
* Conceptual images
* Illustrations

The LLM does not directly modify the article Markdown.

Instead:

```text
Image planner
     |
     v
Image specification
     |
     +---- section_id
     +---- placement
     +---- purpose
     +---- alt
     +---- caption
     |
     v
Python
     |
     +---- prompt generation
     +---- filename generation
     +---- Markdown insertion
```

This prevents images from being grouped at the end of the article.

## Image Generation Provider

Cloudflare Workers AI is used to generate images.

The current image model is configurable through the environment.

Generated images are saved in:

```text
images/
```

Failed image generation does not invalidate the article. The failure is logged and the article continues without that image.

## Markdown Processing

Markdown operations are handled by Python.

The application performs:

* Section detection
* Image insertion
* Safe image filename generation
* Image path construction
* Final Markdown validation
* Blog storage

The LLM is not responsible for manipulating the final document structure.

## Validation

Before saving the final article, the validator checks for issues such as:

* Missing H1 title
* Unresolved image placeholders
* Image-generation failure text leaking into the article
* Unsupported-claim markers leaking into the final Markdown
* Unclosed code fences

The validator is deterministic and does not require another LLM call.

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
* Google AI Studio API key
* Tavily API key
* Cloudflare account with Workers AI access

LangSmith is optional.

## Installation

Clone the repository:

```bash
git clone https://github.com/RajabDildar/blog-agent.git
cd blog-agent
```

Install dependencies:

```bash
uv sync
```

Create the environment file:

```bash
cp .env.example .env
```

Then add the required API keys and model configuration.

## Environment Variables

Example:

```env
GROQ_API_KEY=

GROQ_WRITER_MODEL=llama-3.3-70b-versatile
GROQ_REVISION_MODEL=llama-3.3-70b-versatile

GOOGLE_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite

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

Do not commit `.env` to the repository.

## Running the Agent

Start the application with:

```bash
uv run python3 main.py
```

The application prompts for a topic:

```text
Enter blog topic: AI in finance
```

After the graph completes, the generated Markdown blog is saved to:

```text
generated_blogs/
```

Generated images are saved to:

```text
images/
```

## Evaluation

The `eval/` directory contains a small topic set for evaluating the quality of generated blogs.

Recommended evaluation criteria:

* Overall quality
* Structure
* Technical accuracy
* Research quality
* Coherence
* Usefulness
* Writing quality
* Citation quality
* Image quality

Generation metrics can also be tracked:

* Generation time
* LLM calls
* Research calls
* Image calls
* Revision count

The evaluation topics are intended to provide a consistent baseline when changing prompts, models, graph behavior, or research strategies.

## API Usage Strategy

The project is designed for a limited number of high-quality generations rather than high-volume generation.

API usage is distributed across providers:

```text
Gemini
  Research
  Planning
  Editorial review
  Image planning

Groq
  Section writing
  Targeted revision

Tavily
  Web research

Cloudflare Workers AI
  Image generation
```

This avoids depending entirely on one provider and reserves the larger Groq model for the parts of the workflow that directly affect writing quality.

Groq requests are rate-limited and retried when rate-limit errors occur.

## Design Principles

### LLMs make decisions, Python enforces structure

The project keeps deterministic operations outside the LLM.

Examples:

```text
LLM:
Choose image placement

Python:
Insert image into Markdown
```

```text
LLM:
Identify sections requiring revision

Python:
Route those sections and replace them
```

```text
LLM:
Generate article structure

Python:
Preserve section order
```

### Structured outputs

The application uses Pydantic models for major LLM operations including:

* Routing
* Research
* Planning
* Section generation
* Editorial review
* Image planning

### Bounded execution

The graph intentionally avoids unrestricted loops.

The normal flow is:

```text
Route
  ↓
Research when needed
  ↓
Plan
  ↓
Parallel writing
  ↓
Merge
  ↓
Editorial review
  ↓
One targeted revision when necessary
  ↓
Image planning
  ↓
Image generation
  ↓
Validation
  ↓
Save
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
