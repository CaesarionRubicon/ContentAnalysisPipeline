# Content Analysis Pipeline

**Note to self:** Update the Conversation Recovery Guide whenever adding a new subcommand or phase.

# This project aims to build a pipeline for ingesting, analyzing, and querying video and audio content, with a focus on enabling semantic search and preparing for AI-driven content creation tasks.

---

## Table of Contents

- [Project Goal](#project-goal)  
- [Project Structure](#project-structure)  
- [Setup](#setup)  
- [Pipeline Phases](#pipeline-phases)  
- [Unified CLI Usage](#unified-cli-usage)  
- [Testing & Quality](#testing--quality)  
- [CI / GitHub Actions](#ci--github-actions)  
- [Next Steps / Roadmap](#next-steps--roadmap)  
- [Troubleshooting](#troubleshooting)  
- [Conversation Recovery Guide](#conversation-recovery-guide)  

---

## Project Goal

To create a streamlined video editing and creation pipeline leveraging AI capabilities like precise clip retrieval (semantic search filtered by metadata), summarization, and potentially automated editing suggestions, driven by natural language interaction and enriched metadata.

---

## Project Structure
.
├── config/
│   └── config.py                # DB/API keys, paths, environment loader
├── scripts/
│   ├── init.py
│   ├── setup_database.py        # Schema setup & extension enablement
│   ├── db_utils.py              # Postgres connection helpers
│   ├── ingest_data.py           # Media registration & transcription
│   ├── generate_embeddings.py   # SentenceTransformer embeddings
│   ├── generate_entities.py     # spaCy NER
│   ├── generate_summaries.py    # OpenAI GPT summaries
│   ├── generate_tags.py         # HuggingFace Zero-Shot tags
│   ├── query_pipeline.py        # Semantic search + tag filters + prompts
│   ├── retrieve_clips.py        # ffmpeg clip extractor
│   ├── concatenate_clips.py     # ffmpeg clip assembler
│   └── pipeline.py              # Master CLI wrapper
├── tests/                       # pytest suite
├── .github/
│   └── workflows/ci.yml         # GitHub Actions workflow
├── outputs/                     # Generated clips, logs, assembled videos
├── requirements.txt             # Python dependencies
├── .flake8                      # Linting rules
└── README.md


---

## Setup

1. Clone & enter the project:

   ```bash
   git clone <repo_url> && cd ContentAnalysisPipeline
Create & activate a Python virtual environment:

# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
# python3 -m venv venv
# source venv/bin/activate
Install dependencies:

pip install -r requirements.txt
Download spaCy model:

python -m spacy download en_core_web_sm
Configure environment variables: create a .env in the project root with:

DB_NAME=content_creation
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
OPENAI_API_KEY=sk-...
Initialize the database schema:

python -m scripts.setup_database
Prerequisites
Python 3.x
PostgreSQL (v17) with pgvector extension
Git
MediaInfo library (Download)
FFmpeg in your system PATH
(Optional) NVIDIA GPU + CUDA for Whisper GPU mode
Pipeline Phases
Ingest
Register media, extract metadata, generate transcripts via Whisper.
Script: scripts/ingest_data.py

Enrichment

Embeddings (scripts/generate_embeddings.py)
Named Entities (scripts/generate_entities.py)
Summaries (scripts/generate_summaries.py)
Tags (scripts/generate_tags.py)
Query & Clip Retrieval

Semantic search + tag filters (scripts/query_pipeline.py)
Interactive or batch clip extraction (scripts/retrieve_clips.py with --extract-all)
Assemble clips (scripts/concatenate_clips.py)
Cleanup
Remove all generated clips & assemblies:
scripts/pipeline.py clean

Unified CLI Usage
All through the master CLI: scripts/pipeline.py

Ingest media:

python scripts/pipeline.py ingest --file path/to/video.mp4
Enrich data:

python scripts/pipeline.py enrich
Query (with extraction & assembly):

python scripts/pipeline.py query "your query" -n 5 --extract-all --assemble
Extract single clip:

python scripts/pipeline.py extract \
  --source-uri file:///...mp4 \
  --start-sec 10 --end-sec 15
Assemble clips:

python scripts/pipeline.py assemble \
  --input-dir outputs/clips \
  --output-file outputs/assembled/combined.mp4
Clean outputs:

python scripts/pipeline.py clean
Run --help on any subcommand for details:

python scripts/pipeline.py <subcommand> --help
Log files live under outputs/logs/ (e.g. ingestion.log, embedding_generation.log).

Testing & Quality
Unit Tests: tests/ (pytest)
Coverage: pytest-cov, Codecov integration
Linting: flake8 (.flake8)
Run locally:

pytest --cov=scripts --cov-report=term-missing
flake8
CI / GitHub Actions
Workflow in .github/workflows/ci.yml triggers on push & pull_request to main:

Checkout code
Setup Python & install deps
Lint (flake8)
Run tests with coverage (pytest + XML)
Upload coverage to Codecov
Next Steps / Roadmap
Integration tests on a dummy media file
Docker & docker-compose orchestration
Parallel processing with Celery/RQ
Monitoring & centralized logging (ELK/Sentry)
REST API / Web UI (FastAPI)
Extra enrichment: sentiment, face/object detection, multilingual
Troubleshooting
ffmpeg not found
Ensure FFmpeg is installed and on your PATH:

ffmpeg -version
Database connection failures
Check your .env values and that PostgreSQL is running:

pg_isready
Conversation Recovery Guide
If you need to start a fresh chat, provide this summary:

Project Goal: AI-driven video analysis & clip retrieval
Location: <project_root>
Key Scripts:
scripts/pipeline.py (Unified CLI)
ingest_data.py → generate_*.py → query_pipeline.py → retrieve_clips.py → concatenate_clips.py
DB Status: Initialized with tables for media, transcripts, embeddings, entities, summaries, tags
Latest Features: Unified CLI, testing suite, flake8 linting, GitHub Actions CI, Codecov
Current Git Branch & Commit:
git branch --show-current
git log -1 --pretty=%H
Open PR/Issues: PR #… / Issue #… (if any)
Next Task: e.g. “Add integration test for dummy clip ingestion”
Reference a Pipeline Phase or Next Steps item to pick up exactly where you left off.

Notes on Changes
Added Conversation Recovery Guide at the end for seamless context handover.
Reformatted all shell commands in fenced code blocks.
Ensured Table of Contents links match section headings.
Inserted a Troubleshooting section for common pitfalls.
Standardized Markdown headings, bullet styling, and backticks for code references.

Once you commit this, your `README.md` will be self-contained, well-structured, and ready to help you—or any AI—pick up exactly where you left off.