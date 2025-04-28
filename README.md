# Content Analysis Pipeline

This project aims to build a pipeline for ingesting, analyzing, and querying video and audio content, with a focus on enabling semantic search and preparing for AI-driven content creation tasks.

## Project Goal

To create a streamlined video editing and creation pipeline leveraging AI capabilities like clip retrieval (semantic search), sound production, and potentially video assembly, driven by natural language interaction.

## Current Status (As of 2025-04-27/28)

*   **Phase 1 (Foundation Setup) Complete:**
    *   Project structure established on Drive D.
    *   Git repository initialized with core files (`.gitignore`, `README.md`, `requirements.txt`).
    *   Python virtual environment (`venv`) set up.
    *   PostgreSQL database (`content_creation`) schema defined and created using `scripts/setup_database.py`, including `pgvector` extension and tables for media, transcripts, embeddings, scenes, objects, faces.
    *   Centralized configuration implemented via `.env` (for secrets) and `config/config.py` (for settings and paths).
*   **Phase 2 (Data Ingestion) Mostly Complete (for single files):**
    *   `scripts/ingest_data.py` created: registers media, extracts metadata (`pymediainfo`), checks for/generates transcripts (`Whisper`), ingests transcripts (`pysrt`).
*   **Phase 3 (Enrichment) Started:**
    *   `scripts/generate_embeddings.py` created to generate Sentence Transformer embeddings for ingested transcripts. ⏳ (Needs testing)

## Setup

1.  **Prerequisites:**
    *   Python 3.x
    *   PostgreSQL Server (v17 used) with `pgvector` extension capability.
    *   Git
    *   MediaInfo library (install from [https://mediaarea.net/en/MediaInfo/Download](https://mediaarea.net/en/MediaInfo/Download)) - needed for metadata extraction.
    *   (Optional but recommended for Whisper) FFmpeg available in system PATH.
    *   (Optional for Whisper GPU) NVIDIA GPU with CUDA installed.
2.  **Clone/Setup Project:** (Assuming you have the code)
    ```bash
    # Navigate to project directory
    cd D:\ContentAnalysisPipeline

    # Create/Activate Virtual Environment
    python -m venv venv
    .\venv\Scripts\activate  # Windows PowerShell/cmd

    # Install Dependencies (including PyTorch for CUDA if using GPU)
    pip install -r requirements.txt
    # Visit pytorch.org for specific command if needed, e.g.:
    # pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

    # Configure Environment
    # Create a .env file in the project root (D:\ContentAnalysisPipeline)
    # Add your database credentials and any necessary API keys:
    # DB_NAME="content_creation"
    # DB_USER="your_db_user"
    # DB_PASSWORD="your_db_password"
    # DB_HOST="localhost"
    # DB_PORT="5432"
    # OPENAI_API_KEY="your_key" # Optional for now
    # GOOGLE_APPLICATION_CREDENTIALS="path/to/google_key.json" # Optional for now

    # Setup Database Schema (Run only once initially or to reset)
    # Ensure PostgreSQL server is running!
    python scripts/setup_database.py
    ```

## Running the Pipeline (Current)

*   **Ingest Data:** (Handles metadata and transcription)
    ```bash
    # Example for a single file:
    python scripts/ingest_data.py --file "D:/path/to/your/video.mp4"

    # Example for a directory:
    python scripts/ingest_data.py --directory "D:/path/to/your/media_folder"
    ```
*   **Generate Embeddings:** (Run after ingesting transcripts)
    ```bash
    python scripts/generate_embeddings.py
    ```
*   Check `outputs/logs/ingestion.log` and `outputs/logs/embedding_generation.log` for detailed logs.

## Next Steps (Blueprint)

1.  **Phase 3 (Enrichment) Continued:**
    *   Test and refine `generate_embeddings.py`. ✅
    *   Implement Semantic Tagging (NER/Topics).
    *   Implement Multi-Layer Summarization.
    *   Implement Advanced Metadata Extraction (Tone/Sentiment).
2.  **Phase 4 (Querying & Application):**
    *   Implement semantic search (`query_pipeline.py`).
    *   Build CLI/API.
    *   Develop content assembly logic.
3.  **Phase 5 (Deployment & Ops):**
    *   Dockerize.
    *   Cloud deployment.
    *   Optimization (Task Queues, Caching).
    *   Monitoring & Feedback Loop.

## Active Scripts

The core, active scripts for this pipeline currently are:
*   `scripts/setup_database.py`
*   `scripts/ingest_data.py`
*   `scripts/generate_embeddings.py`

## Untracked Scripts Warning

The `scripts/_old_scripts_reference/` directory contains many untracked scripts migrated from a previous project version (`VoteCarney2025Ad`). These scripts are **not** currently used by the refactored pipeline and need significant updates. They are being kept temporarily as a reference only and are ignored by Git.