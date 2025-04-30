# Content Analysis Pipeline

This project aims to build a pipeline for ingesting, analyzing, and querying video and audio content, with a focus on enabling semantic search and preparing for AI-driven content creation tasks.

## Project Goal

To create a streamlined video editing and creation pipeline leveraging AI capabilities like precise clip retrieval (semantic search filtered by metadata), summarization, and potentially automated editing suggestions, driven by natural language interaction and enriched metadata.

## Current Status (As of 2025-04-29)

*   **Phase 1 (Foundation Setup) Complete:**
    *   Project structure established (`D:\ContentAnalysisPipeline`).
    *   Git repository initialized (`.gitignore` configured).
    *   Python virtual environment (`venv`) set up (`requirements.txt` maintained).
    *   PostgreSQL database (`content_creation`) schema defined (`scripts/setup_database.py`). `pgvector` enabled. Includes tables: `media`, `transcripts`, `embeddings`, `entities`, `summaries`, `content_tags`, `scenes`, `objects`, `faces`.
    *   Centralized configuration (`.env`, `config/config.py`). Handles DB credentials, API keys, paths. Loads `.env` overriding system vars.
    *   Database utilities (`scripts/db_utils.py`).
*   **Phase 2 (Data Ingestion) Complete (for file workflow):**
    *   `scripts/ingest_data.py`: Handles media registration (from files), extracts metadata (`pymediainfo`), checks for/generates transcripts (`Whisper` via SRT), sets initial transcript status to `'pending_enrichment'`. Tested. ✅
*   **Phase 3 (Enrichment) Complete (Core Text Features):**
    *   `scripts/generate_embeddings.py`: Generates Sentence Transformer (`all-MiniLM-L6-v2`) embeddings for transcripts. Tested. ✅
    *   `scripts/generate_entities.py`: Generates Named Entities (NER) using spaCy (`en_core_web_sm`), updates status to `'entities_extracted'`. Tested. ✅
    *   `scripts/generate_summaries.py`: Generates summaries using OpenAI API (`gpt-3.5-turbo`), stores in `summaries` table, updates status to `'summarized'`. Includes `LIMIT 1` for testing. Tested. ✅
    *   `scripts/generate_tags.py`: Generates topic/keyword tags using Hugging Face Zero-Shot Classification (`facebook/bart-large-mnli`), stores in `content_tags` table, updates status to `'tags_generated'`. Includes `LIMIT 1` for testing. Tested. ✅
*   **Phase 4 (Querying & Application) In Progress:**
    *   `scripts/query_pipeline.py`: Performs semantic search, enhanced to filter by tags (`--tag-type`, `--tag-value`) and display summaries/tags in results. Tested. ✅
    *   `scripts/retrieve_clips.py`: New script to extract clips via ffmpeg, integrated into `query_pipeline.py`. ✅

## Setup

1.  **Prerequisites:**
    *   Python 3.x
    *   PostgreSQL Server (v17 used) with `pgvector` extension capability.
    *   Git
    *   MediaInfo library (install from https://mediaarea.net/en/MediaInfo/Download).
    *   FFmpeg available in system PATH.
    *   (Optional for Whisper GPU) NVIDIA GPU with CUDA installed.
2.  **Clone/Setup Project:** (Assuming you have the code)
    ```bash
    # Navigate to project directory
    cd D:\ContentAnalysisPipeline

    # Create/Activate Virtual Environment
    python -m venv venv
    .\venv\Scripts\activate  # Windows PowerShell/cmd

    # Install Dependencies
    pip install -r requirements.txt

    # Download spaCy English model
    python -m spacy download en_core_web_sm

    # Configure Environment
    # Create a .env file in the project root (D:\ContentAnalysisPipeline)
    # Add your database credentials and API key:
    # DB_NAME="content_creation"
    # DB_USER="your_db_user"
    # DB_PASSWORD="your_db_password"
    # DB_HOST="localhost"
    # DB_PORT="5432"
    # OPENAI_API_KEY="sk-..." # Required for summarization

    # Setup/Reset Database Schema (Wipes existing data!)
    python -m scripts.setup_database
    ```

## Running the Pipeline (Current Order - For Full Processing)

1.  **Ingest Data:**
    ```bash
    python scripts/ingest_data.py --file "D:\path\to\your\video.mp4"
    ```
2.  **Generate Embeddings:**
    ```bash
    python scripts/generate_embeddings.py
    ```
3.  **Generate Named Entities:**
    ```bash
    python scripts/generate_entities.py
    ```
4.  **Generate Summaries:**
    ```bash
    python scripts/generate_summaries.py
    ```
5.  **Generate Tags:**
    ```bash
    python scripts/generate_tags.py
    ```
6.  **Query Data:**
    ```bash
    # Simple semantic search
    python scripts/query_pipeline.py "your query text" -n 5

    # Semantic search filtered by tag
    python scripts/query_pipeline.py "your query text" -n 5 --tag-type topic --tag-value "some topic"
    ```
7.  **Extract Clips**
    You can extract clips either interactively via the query script or directly via the retrieval script.

    Method A: Interactive via Query  
      # Run a semantic search; you’ll be prompted to save each clip  
      python scripts/query_pipeline.py "your query text" -n 5  
      # After each result, type "y" to extract the clip to outputs/clips/

    Method B: Direct Clip Extraction  
      # Invoke the retrieval script with explicit times  
      python scripts/retrieve_clips.py \
        --source-uri "path/to/your/video.mp4" \
        --start-sec 30 \
        --end-sec 35 \
        --output-dir outputs/clips

*   Check `outputs/logs/` for detailed logs (`ingestion.log`, `embedding_generation.log`, etc.).

## Next Steps (Blueprint)

1.  **Phase 4 (Querying & Application) Continued:**
    *   Enhance User Interface (CLI/API).
    *   Develop Content Assembly logic.
2.  **Phase 3 (Enrichment) Enhancements (Optional):**
    *   Implement Advanced Sentiment/Tone Analysis.
    *   Implement Multimodal Analysis (Video: Scenes, Objects, Faces).
3.  **Phase 5 (Deployment & Ops):**
    *   Dockerize.
    *   Cloud deployment.
    *   Optimization (Task Queues, Caching, Async Processing).
    *   Monitoring & Feedback Loop.

## Active Scripts

*   `config/config.py`
*   `scripts/setup_database.py`
*   `scripts/db_utils.py`
*   `scripts/ingest_data.py`
*   `scripts/generate_embeddings.py`
*   `scripts/generate_entities.py`
*   `scripts/generate_summaries.py`
*   `scripts/generate_tags.py`
*   `scripts/query_pipeline.py`
*   `scripts/retrieve_clips.py`

## Untracked Scripts Warning

The `scripts/_old_scripts_reference/` directory contains untracked scripts kept for reference only. The `.gitignore` file is configured to ignore `data/`, `outputs/`, `venv/`, `.env`, etc.