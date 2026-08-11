# Blog Agent

A Python-based technical blog generation agent built with **LangGraph**, **LangChain**, **Groq**, **Tavily**, and **Cloudflare AI**.

The agent takes a blog topic from the user, determines whether web research is required, creates a structured blog plan, generates individual sections, combines them into a complete Markdown article, decides whether technical images are useful, generates those images when required, and saves the final blog locally.

## Features

* Topic-based technical blog generation
* Automatic research routing
* Web research using Tavily
* Structured blog planning with Pydantic
* Parallel section generation using LangGraph `Send`
* Markdown blog generation
* Automatic technical image/diagram planning
* Image generation using Cloudflare AI
* Automatic image insertion into generated Markdown
* Generated blogs stored in a dedicated `generated_blogs/` directory
* Generated images stored in the `images/` directory
* Groq rate limiting
* Retry handling for Groq rate-limit errors
* Modular project structure separating schemas, nodes, services, and graph construction
* Dependency management with [uv](https://docs.astral.sh/uv/)

---

## How It Works

The agent follows this workflow:

```text
User enters topic
        │
        ▼
      Router
        │
        ├──────────────────┐
        │                  │
        ▼                  ▼
   No research          Research
        │                  │
        │                  ▼
        │             Tavily Search
        │                  │
        │                  ▼
        │               Evidence
        │                  │
        └─────────┬────────┘
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
       Worker   Worker   Worker ...
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

The program runs once for the topic provided by the user and then exits.

---

## Project Structure

```text
blog-agent/
│
├── LICENSE
├── README.md
├── main.py
├── pyproject.toml
├── uv.lock
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
└── images/
    └── generated images
```

### Directory Responsibilities

### `main.py`

The application entry point.

It asks the user for a blog topic and passes that topic to the LangGraph application.

```python
from graph.main_graph import run


topic = input("Enter the blog topic: ")

run(topic)
```

The program does not contain an interactive loop. It accepts one topic, runs the agent, saves the output, and exits.

---

### `config/`

Contains application configuration.

`settings.py` contains:

* Environment variable loading
* Groq rate limiter configuration
* LangGraph retry policy

---

### `schemas/`

Contains the data structures used throughout the application.

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

Runs Tavily searches and converts raw search results into structured evidence.

#### `orchestrator.py`

Creates the blog plan.

The plan contains:

* Blog title
* Audience
* Tone
* Blog type
* Constraints
* Writing tasks

#### `worker.py`

Generates individual blog sections.

LangGraph uses `Send` to distribute the writing tasks to worker nodes.

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

Contains the LangGraph construction.

#### `reducer_graph.py`

Builds the reducer subgraph:

```text
merge_content
      │
      ▼
decide_images
      │
      ▼
generate_and_place_images
```

#### `main_graph.py`

Builds the main application graph:

```text
router
   │
   ├── research ─────┐
   │                 │
   └─────────────────┤
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

# Requirements

You need:

* Python 3.10+
* [uv](https://docs.astral.sh/uv/)
* A Groq API key
* A Tavily API key
* A Cloudflare account ID and API token for image generation

The project's Python dependencies are defined in `pyproject.toml`.

The exact dependency versions resolved for the project are stored in `uv.lock`.

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/RajabDildar/blog-agent.git
cd blog-agent
```

---

## 2. Install uv

This project uses **uv** for Python environment and dependency management.

### Linux

Install uv with:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal if necessary.

Verify the installation:

```bash
uv --version
```

You can also install uv through your Linux distribution or package manager if preferred.

### Windows

Using PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then verify:

```powershell
uv --version
```

Alternatively, uv can be installed through other supported Windows package managers. See the official uv installation documentation for additional options.

---

## 3. Install project dependencies

From the project root:

```bash
uv sync
```

`uv` will create the project's virtual environment and install the dependencies defined by `pyproject.toml`.

The existing `uv.lock` file is used to keep dependency versions consistent.

---

# Environment Variables

The agent requires API credentials for the external services it uses.

Create a `.env` file in the project root:

```text
blog-agent/
├── .env
├── main.py
├── pyproject.toml
└── ...
```

Add:

```env
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

Replace the placeholder values with your actual credentials.

### Important

Do not commit `.env` to Git.

Your `.gitignore` should contain:

```gitignore
.env
.venv/
__pycache__/
*.pyc
```

---

# Running the Project

The project uses `uv` to run the application.

## Linux

From the project root:

```bash
uv run python3 main.py
```

The application will ask:

```text
Enter the blog topic:
```

For example:

```text
Enter the blog topic: AI in Finance
```

The agent will then execute the complete workflow.

You do not need to manually activate the virtual environment when using `uv run`.

---

## Windows

From PowerShell or Command Prompt, run:

```powershell
uv run python main.py
```

Then enter your topic:

```text
Enter the blog topic: AI in Finance
```

The application will execute the agent and exit when the blog generation process finishes.

---

# Output

Generated blogs are stored in:

```text
generated_blogs/
```

For example:

```text
generated_blogs/
└── AI in Finance.md
```

Generated images are stored in:

```text
images/
```

For example:

```text
images/
├── ai_finance_architecture.png
└── ai_finance_workflow.png
```

The project keeps generated Markdown files separate from the source code so the project root does not become cluttered with generated articles.

---

# Image References

Because Markdown files are stored inside `generated_blogs/` while images are stored inside `images/`, generated Markdown files reference images using paths relative to the Markdown file.

For example:

```markdown
![AI finance architecture](../images/ai_finance_architecture.png)
```

The project structure is:

```text
blog-agent/
│
├── generated_blogs/
│   └── AI in Finance.md
│
└── images/
    └── ai_finance_architecture.png
```

The `../images/` path moves from `generated_blogs/` back to the project root and then into `images/`.

This allows Markdown renderers to correctly locate the generated images.

---

# Research Modes

Before creating the blog plan, the router determines whether web research is required.

## Closed Book

Used for evergreen topics where current information is not required.

```text
Topic
  │
  ▼
Router
  │
  ▼
closed_book
  │
  ▼
Orchestrator
```

---

## Hybrid

Used for topics that are mostly evergreen but may benefit from current tools, models, releases, or examples.

```text
Topic
  │
  ▼
Router
  │
  ▼
hybrid
  │
  ▼
Research
  │
  ▼
Evidence
  │
  ▼
Orchestrator
```

---

## Open Book

Used for topics that depend heavily on current information, such as recent events, latest developments, rankings, pricing, policies, or regulations.

```text
Topic
  │
  ▼
Router
  │
  ▼
open_book
  │
  ▼
Research
  │
  ▼
Evidence
  │
  ▼
Orchestrator
```

---

# Blog Planning

The orchestrator creates a structured `Plan`.

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

This structure allows individual worker nodes to generate different sections of the blog.

---

# Parallel Section Generation

The project uses LangGraph's `Send` mechanism to distribute blog-writing tasks.

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

The generated sections are later ordered according to their task IDs before being combined into the final article.

---

# Image Generation

After the blog sections are merged, the agent determines whether technical images or diagrams are useful.

When images are requested, the image planner produces image specifications containing:

```text
Placeholder
Filename
Alt text
Caption
Prompt
Size
Quality
```

The Cloudflare AI service is then used to generate the requested images.

Generated images are stored in:

```text
images/
```

and inserted into the generated Markdown document.

---

# Image Generation Failure

If an individual image generation request fails, the entire blog does not need to fail.

The failed image placeholder is replaced with information about the failed generation request, allowing the Markdown blog to still be saved.

---

# Generated Blog Example

Running:

```bash
uv run python3 main.py
```

and entering:

```text
Enter the blog topic: AI Agents
```

can produce:

```text
generated_blogs/
└── AI Agents.md

images/
├── agent_architecture.png
├── agent_workflow.png
└── tool_calling_flow.png
```

The generated Markdown contains references such as:

```markdown
![Agent architecture](../images/agent_architecture.png)
```

---

# Development

The project uses `uv` for dependency management.

After changing dependencies, use:

```bash
uv add package-name
```

For example:

```bash
uv add requests
```

To remove a dependency:

```bash
uv remove package-name
```

To synchronize the environment with the project's dependency configuration:

```bash
uv sync
```

To run the application:

```bash
uv run python3 main.py
```

On Windows:

```powershell
uv run python main.py
```

---

# License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for the complete license text.

The MIT License permits use, copying, modification, distribution, sublicensing, and sale of copies of the software, subject to the conditions stated in the license.

---

## Author

**Rajab Dildar**

GitHub: [@RajabDildar](https://github.com/RajabDildar)
