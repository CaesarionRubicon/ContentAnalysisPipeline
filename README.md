# Content Analysis Pipeline

This project aims to build a pipeline for ingesting, analyzing, and querying video and audio content, with a focus on enabling semantic search and preparing for AI-driven content creation tasks.

## Project Goal

To create a streamlined video editing and creation pipeline leveraging AI capabilities like clip retrieval (semantic search), sound production, and potentially video assembly, driven by natural language interaction.

## Current Status (As of 2025-04-27)

*   **Phase 1 (Foundation Setup) Complete:**
    *   Project structure established on Drive D.
    *   Git repository initialized with core files (`.gitignore`, `README.md`, `requirements.txt`).
    *   Python virtual environment (`venv`) set up.
    *   PostgreSQL database (`content_creation`) schema defined and created using `scripts/setup_database.py`, including `pgvector` extension and tables for media, transcripts, embeddings, scenes, objects, faces.
    *   Centralized configuration implemented via `.env` (for secrets) and `config/config.py` (for settings and paths).
*   **Phase 2 (Data Ingestion) Started:**
    *   Basic `scripts/ingest_data.py` created with logging, argument parsing (for file/directory input), and functionality to register media files (video, audio, image based on extension) in the `media` table.

## Setup

1.  **Prerequisites:**
    *   Python 3.x
    *   PostgreSQL Server (v17 used) with `pgvector` extension capability.
    *   Git
2.  **Clone/Setup Project:** (Assuming you have the code)
    ```bash
    # Navigate to project directory
    cd D:\ContentAnalysisPipeline

    # Create/Activate Virtual Environment
    python -m venv venv
    .\venv\Scripts\activate  # Windows PowerShell/cmd

    # Install Dependencies
    pip install -r requirements.txt

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

*   **Ingest Data:**
    *   To ingest a single file:
        ```bash
        python scripts/ingest_data.py --file "D:/path/to/your/video.mp4"
        ```
    *   To ingest all files in a directory:
        ```bash
        python scripts/ingest_data.py --directory "D:/path/to/your/media_folder"
        ```
    *   Check `outputs/logs/ingestion.log` for detailed logs.

## Next Steps (Blueprint)

1.  **Phase 2 (Ingestion) Continued:**
    *   Extract basic metadata (duration, etc.) in `ingest_data.py`.
    *   Implement ingestion of existing transcript files (`.srt`).
    *   Integrate automated transcription (e.g., Whisper).
    *   Integrate scene detection.
    *   Integrate Google VI JSON metadata parsing.
2.  **Phase 3 (Processing & Enrichment):**
    *   Implement embedding generation (`generate_embeddings.py`).
    *   Implement summarization (optional).
    *   Implement object/face detection (optional).
3.  **Phase 4 (Querying & Application):**
    *   Implement semantic search (`query_pipeline.py`).
    *   Build CLI/API.
    *   Develop content assembly logic.
4.  **Phase 5 (Deployment & Ops):**
    *   Dockerize.
    *   Cloud deployment.
    *   Optimization.

## Untracked Scripts Warning

The `scripts/` directory currently contains many untracked scripts migrated from a previous project version (`VoteCarney2025Ad`). These scripts are **not** currently used by the refactored pipeline and need significant updates to work with the new structure and database schema. They are being kept temporarily as a reference for migrating logic. The core, active scripts for this pipeline are:
*   `scripts/setup_database.py`
*   `scripts/ingest_data.py` (in progress)
*   (Future: `generate_embeddings.py`, `query_pipeline.py`, etc.)