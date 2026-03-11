---
title: Codebase Reader
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# Codebase Reader 🤖📚

A multi-agent Python system that accepts a public GitHub repository URL and produces high-quality Markdown documentation — complete with prose explanations and auto-generated diagrams.

---

## System Architecture

```
GitHub URL
    │
    ▼
┌─────────────────────────────────────────────────────┐
│              Code Genius (Supervisor)               │
│  Orchestrates the pipeline, prioritises analysis    │
└──────┬──────────┬────────────────┬──────────────────┘
       │          │                │
       ▼          ▼                ▼
 Repo Mapper  Code Analyzer    DocGenie
 ─────────── ─────────────── ─────────────
 • Clone      • Tree-sitter   • Markdown
 • File tree    parsing         generation
 • README     • Code Context  • Diagrams
   summary      Graph (CCG)   • File output
```

### Agents

| Agent | Module | Responsibility |
|---|---|---|
| **Code Genius** | `agents/supervisor.py` | Orchestrator — delegates, aggregates, assembles |
| **Repo Mapper** | `agents/repo_mapper.py` | Clone repo, build file tree, summarise README |
| **Code Analyzer** | `agents/code_analyzer.py` | Parse source, build CCG, answer queries |
| **DocGenie** | `agents/doc_genie.py` | Generate & save Markdown documentation |

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A Google Gemini **or** OpenAI API key

---

## Setup

```bash
# 1. Clone / navigate to this project
cd "d:\Gen AI Course\Readme_agent"

# 2. Create virtual environment (already done if you followed setup)
uv venv

# 3. Activate the environment
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 4. Install dependencies
uv pip install -e ".[dev]"

# 5. Configure environment
copy .env.example .env
# Edit .env and add your API key
```

---

## Running the API Server

```bash
uvicorn agentic_codebase_reader.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## API Usage

### Analyse a repository

```bash
curl -X POST http://localhost:8000/analyze \
     -H "Content-Type: application/json" \
     -d '{"repo_url": "https://github.com/owner/repo"}'
```

### Download generated documentation

```bash
curl http://localhost:8000/download/{repo_name} --output docs.md
```

---

## Running from the CLI

```bash
codebase-reader https://github.com/owner/repo
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Generated Output

Documentation is saved to:

```
outputs/<repo_name>/docs.md
```

---

## Project Structure

```
agentic_codebase_reader/
├── agents/          # The four agents
├── models/          # Pydantic data models
├── services/        # Git, parser, LLM, diagram utilities
├── api/             # FastAPI HTTP layer
└── config.py        # Settings loaded from .env
```
