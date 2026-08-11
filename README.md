# Blog Agent

A Python-based technical blog generation agent built with LangGraph, LangChain, Groq, Tavily, and Cloudflare AI.

The agent takes a blog topic from the user, determines whether web research is required, creates a structured blog plan, generates individual sections, combines them into a complete Markdown article, decides whether technical images are useful, generates those images when required, and saves the final blog locally.

## Features

* Topic-based blog generation
* Automatic research routing
* Web research using Tavily
* Structured blog planning using Pydantic models
* Parallel section generation using LangGraph `Send`
* Technical Markdown generation
* Automatic image/diagram planning
* Image generation using Cloudflare AI
* Automatic image insertion into generated Markdown
* Markdown output saved in a dedicated `generated_blogs/` directory
* Generated images saved in the `images/` directory
* Groq rate limiting and retry handling
* Modular project structure with separation between schemas, nodes, services, and graph construction

---

## How the Agent Works

The application follows this general flow:

```text
User enters topic
        │
        ▼
      Router
        │
        ├───────────────┐
        │               │
        ▼               ▼
   No research       Research
        │               │
        │               ▼
        │          Tavily Search
        │               │
        │               ▼
        │           Evidence
        │               │
        └───────┬───────┘
                ▼
          Orchestrator
                │
                ▼
          Blog Plan
                │
                ▼
             Fanout
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
     Worker  Worker   Worker ...
        │       │        │
        └───────┼────────┘
                ▼
        Merge Sections
                │
                ▼
         Decide Images
                │
                ▼
      Generate / Place Images
                │
                ▼
       Save Markdown Blog
                │
                ▼
               END
```

The application executes once for the topic entered by the user and then exits.

---

## Project Structure

```text
.
├── main.py
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── schemas/
│   ├── __init__.py
│   ├── models.py
│   └── state.py
│
├── nodes/
│   ├── __init__.py
│   ├── router.py
│   ├── research.py
│   ├── orchestrator.py
│   ├── worker.py
│   └── reducer.py
│
├── services/
│   ├── __init__.py
│   ├── llm.py
│   ├── tavily.py
│   └── cloudflare.py
│
├── graph/
│   ├── __init__.py
│   ├── reducer_graph.py
│   └── main_graph.py
│
├── generated_blogs/
│   └── generated Markdown files
│
├── images/
│   └── generated images
│
├── .env
├── requirements.txt
└── README.md
```

### Directory Responsibilities

#### `main.py`

The application entry point.

It asks the user for a blog topic and passes that topic to the LangGraph application.

```python
from graph.main_graph import run


topic = input("Enter the blog topic: ")

run(topic)
```

---

### `config/`

Contains application-level configuration.

`settings.py` contains:

* Environment variable loading
* Groq rate limiter configuration
* LangGraph retry policy

---

### `schemas/`

Contains the application's data structures.

`models.py` contains the Pydantic models used by the agent, including:

* `Task`
* `Plan`
* `EvidenceItem`
* `RouterDecision`
* `EvidencePack`
* `ImageSpec`
* `GlobalImagePlan`

`state.py` contains the LangGraph `State` definition.

---

### `nodes/`

Contains the individual LangGraph nodes.

#### `router.py`

Determines whether the topic requires web research.

The router can select:

* `closed_book`
* `hybrid`
* `open_book`

When research is required, it also generates search queries.

#### `research.py`

Runs the requested Tavily searches and converts the raw search results into structured evidence.

#### `orchestrator.py`

Creates the blog plan.

The plan contains the blog title, audience, tone, blog type, constraints, and individual writing tasks.

#### `worker.py`

Generates one blog section per task.

LangGraph uses `Send` to fan the tasks out to workers.

#### `reducer.py`

Handles the final stages of the workflow:

1. Merge generated sections
2. Decide whether images are needed
3. Generate requested images
4. Insert images into the Markdown
5. Save the final blog

---

### `services/`

Contains external service integrations.

#### `llm.py`

Creates the Groq `ChatGroq` model used by the application.

#### `tavily.py`

Contains the Tavily search functionality.

#### `cloudflare.py`

Contains the Cloudflare AI image generation request.

---

### `graph/`

Contains LangGraph construction.

#### `reducer_graph.py`

Builds the reducer subgraph:

```text
merge_content
      ↓
decide_images
      ↓
generate_and_place_images
```

#### `main_graph.py`

Builds the main application graph:

```text
router
   │
   ├── research ──┐
   │              │
   └──────────────┤
                  ▼
             orchestrator
                  │
                  ▼
                worker
                  │
                  ▼
               reducer
                  │
                  ▼
                 END
```

---

## Requirements

The project requires Python and the Python packages listed in `requirements.txt`.

The application uses:

* Python
* LangGraph
* LangChain
* LangChain Groq
* LangChain Tavily
* Pydantic
* Groq
* Requests
* python-dotenv

---

## Environment Variables

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

Do not commit the `.env` file to Git.

Add it to `.gitignore`:

```gitignore
.env
__pycache__/
*.pyc
```

---

## Installation

Clone or create the project and move into its root directory.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

---

## Running the Agent

Run:

```bash
python main.py
```

The program asks for the blog topic:

```text
Enter the blog topic: AI Agents
```

The agent then runs the complete workflow.

After the workflow finishes, the program exits.

---

## Generated Output

Generated Markdown files are saved inside:

```text
generated_blogs/
```

For example:

```text
generated_blogs/
└── AI Agents.md
```

Generated images are saved inside:

```text
images/
```

For example:

```text
images/
├── ai_agent_architecture.png
└── agent_workflow.png
```

The generated Markdown references images relative to its own location.

For example:

```markdown
![AI agent architecture](../images/ai_agent_architecture.png)
```

This allows Markdown renderers to correctly locate images from files stored inside `generated_blogs/`.

---

## Research Routing

Before creating the blog plan, the router determines whether web research is needed.

### Closed Book

Used for topics where current information is not required.

```text
Topic
  ↓
Router
  ↓
closed_book
  ↓
Orchestrator
```

### Hybrid

Used when the topic is mostly evergreen but current tools, models, releases, or examples may be useful.

```text
Topic
  ↓
Router
  ↓
hybrid
  ↓
Research
  ↓
Evidence
  ↓
Orchestrator
```

### Open Book

Used for topics that depend heavily on current information, such as latest developments, rankings, pricing, policies, or recent events.

```text
Topic
  ↓
Router
  ↓
open_book
  ↓
Research
  ↓
Evidence
  ↓
Orchestrator
```

---

## Blog Planning

The orchestrator generates a structured `Plan`.

A plan contains:

```text
Blog title
Audience
Tone
Blog kind
Constraints
Tasks
```

Each task contains:

```text
Task ID
Section title
Goal
Bullets
Target word count
Tags
Research requirement
Citation requirement
Code requirement
```

This structure allows the worker nodes to generate individual sections independently.

---

## Parallel Section Generation

The project uses LangGraph's `Send` mechanism to distribute blog-writing tasks to worker nodes.

Conceptually:

```text
                    Blog Plan
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     Worker 1       Worker 2       Worker 3
        │              │              │
        ▼              ▼              ▼
    Section 1      Section 2      Section 3
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                   Reducer
```

The generated sections are later ordered according to their task IDs.

---

## Image Generation

After the sections are merged, the agent decides whether technical images or diagrams are useful.

The image planning stage can generate up to three image specifications.

Each image specification contains:

```text
Placeholder
Filename
Alt text
Caption
Prompt
Size
Quality
```

If images are requested, the Cloudflare AI service generates the image bytes.

The images are saved to:

```text
images/
```

and inserted into the generated Markdown.

---

## Output Example

After running:

```bash
python main.py
```

and entering:

```text
Enter the blog topic: AI Agents
```

the project may produce:

```text
generated_blogs/
└── AI Agents.md

images/
├── agent_architecture.png
├── agent_workflow.png
└── tool_calling_flow.png
```

The generated Markdown contains the corresponding image references.

---

## Error Handling During Image Generation

If an image cannot be generated, the blog remains usable.

Instead of stopping the entire blog generation process, the failed image placeholder is replaced with information about the failed image generation request.

The Markdown document can therefore still be saved even when an individual image generation request fails.

---

## Current Execution Model

The application is intentionally a single-run program.

```text
Start
  ↓
Ask for topic
  ↓
Run agent
  ↓
Generate blog
  ↓
Save blog/images
  ↓
Exit
```

There is no interactive loop in `main.py`.

---
