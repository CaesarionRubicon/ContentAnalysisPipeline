# VoteCarney2025Ad Project

Satirical political campaign ad for Mark Carney.

Folder structure:
- raw_video/: source footage
- audio/: voice‑overs, SFX, music
- transcripts/: auto‑generated JSON/SRT
- graphics/: logos, overlays, PNGs
- scripts/: Python & shell scripts
- outputs/: rendered drafts and final cuts
- data/: model files, scene timestamps
- logs/: detection logs
- backups/: manual archives


# Content Creation Pipeline with PostgreSQL and pgvector

This project has evolved into a generalized content creation pipeline for analyzing video metadata, transcripts, and embeddings using PostgreSQL with the pgvector extension. The pipeline supports semantic search with AI to retrieve specific video clips (e.g., "character drinking a cup of water").

## Database Setup
- **Database**: PostgreSQL 17 with pgvector extension.
- **Schema**:
  - `videos`: Stores video metadata (id, filename, duration, title, url).
  - `scenes`: Stores scene timestamps (id, video_id, start_sec, end_sec).
  - `transcripts`: Stores transcript segments (id, video_id, start_sec, end_sec, text).
  - `objects`: Stores object detection data (id, video_id, start_sec, end_sec, label, confidence).
  - `faces`: Stores face detection data (id, video_id, start_sec, end_sec, face_id, confidence).
  - `embeddings`: Stores vector embeddings for semantic search (id, scene_id, description, embedding as vector(384)).

## Scripts
- **migrate_to_postgres.py**: Ingests data from local files (Google JSON, SRT transcripts, CSV scene logs) into the PostgreSQL database.
  - Command: `python scripts/migrate_to_postgres.py`
- **generate_embeddings.py**: Generates embeddings for scenes using `sentence-transformers` (`all-MiniLM-L6-v2`) and stores them in the `embeddings` table.
  - Command: `python scripts/generate_embeddings.py`
- **query_llm.py**: Queries the database for clips using semantic search with a natural language query.
  - Command: `python scripts/query_llm.py --query "character drinking a cup of water" --limit 3`

## Setup Instructions
1. Ensure PostgreSQL 17 and pgvector are installed (see earlier sections).
2. Activate the virtual environment: `.\venv\Scripts\activate`
3. Install dependencies: `pip install psycopg2-binary sentence-transformers pandas openpyxl pysrt click`
4. Create the `content_creation` database in PostgreSQL and enable pgvector:

   CREATE DATABASE content_creation;
   \c content_creation
   CREATE EXTENSION vector;

5. Run the ingestion script to populate the database: `python scripts/migrate_to_postgres.py`
6. Generate embeddings: `python scripts/generate_embeddings.py`
7. Query for clips: `python scripts/query_llm.py --query "your query" --limit 5`

## Future Enhancements
- Pull bulk data from YouTube using `yt-dlp` (e.g., metadata, transcripts, scene timestamps).
- Add support for more data sources (e.g., Vimeo, TikTok, cloud storage).
- Integrate advanced LLMs (e.g., OpenAI) for query refinement or content generation.
- Add a web interface for easier querying.
- Scale with table partitioning or dedicated vector stores (e.g., Pinecone, Weaviate).



