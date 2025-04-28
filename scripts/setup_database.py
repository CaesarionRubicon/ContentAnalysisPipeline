import os
import psycopg2
from psycopg2 import sql
import sys
from pathlib import Path # Use pathlib

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent # More robust way to get project root
sys.path.append(str(PROJECT_ROOT))

from config import config # Import the config module from the config directory

# --- SQL Commands ---

# Drop existing schema and tables if they exist (for a clean reset)
DROP_SCHEMA_SQL = """
DROP SCHEMA IF EXISTS content_creation CASCADE;
"""

# Create the schema
CREATE_SCHEMA_SQL = """
CREATE SCHEMA content_creation;
"""

# Create the media table
CREATE_MEDIA_TABLE_SQL = """
CREATE TABLE content_creation.media (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    source_uri VARCHAR(1024) NOT NULL UNIQUE,
    media_type VARCHAR(20) NOT NULL,
    title VARCHAR(255),
    duration REAL,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the scenes table
CREATE_SCENES_TABLE_SQL = """
CREATE TABLE content_creation.scenes (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the transcripts table
CREATE_TRANSCRIPTS_TABLE_SQL = """
CREATE TABLE content_creation.transcripts (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL,
    end_sec REAL,
    text TEXT NOT NULL,
    confidence REAL,
    status VARCHAR(50) DEFAULT 'pending_enrichment', -- Status workflow: pending_enrichment -> entities_extracted -> summarized -> tags_generated -> complete?
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""
CREATE_TRANSCRIPTS_INDEX_SQL = """
CREATE INDEX idx_transcripts_media_time ON content_creation.transcripts (media_id, start_sec, end_sec);
"""

# Create the objects table
CREATE_OBJECTS_TABLE_SQL = """
CREATE TABLE content_creation.objects (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    label VARCHAR(255) NOT NULL,
    confidence REAL,
    bounding_box JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the faces table
CREATE_FACES_TABLE_SQL = """
CREATE TABLE content_creation.faces (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    face_id VARCHAR(255),
    confidence REAL,
    bounding_box JSONB,
    embedding BYTEA,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Enable pgvector extension
ENABLE_PGVECTOR_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
"""

# Create embeddings table
CREATE_EMBEDDINGS_TABLE_SQL = """
CREATE TABLE content_creation.embeddings (
    id SERIAL PRIMARY KEY,
    media_id INTEGER REFERENCES content_creation.media(id) ON DELETE CASCADE,
    transcript_id INTEGER REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    description TEXT,
    model_name VARCHAR(100),
    embedding VECTOR(384) NOT NULL, -- Using config.EMBEDDING_DIMENSION value
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_embedding_source CHECK (media_id IS NOT NULL OR transcript_id IS NOT NULL )
);
"""
CREATE_EMBEDDINGS_INDEX_SQL = """
CREATE INDEX ON content_creation.embeddings USING hnsw (embedding vector_cosine_ops);
"""

# Create entities table
CREATE_ENTITIES_TABLE_SQL = """
CREATE TABLE content_creation.entities (
    id SERIAL PRIMARY KEY,
    transcript_id INTEGER NOT NULL REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    label VARCHAR(50) NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""
CREATE_ENTITIES_INDEX_SQL = """
CREATE INDEX idx_entities_transcript_label ON content_creation.entities (transcript_id, label);
"""
CREATE_ENTITIES_MEDIA_INDEX_SQL = """
CREATE INDEX idx_entities_media_label ON content_creation.entities (media_id, label);
"""

# Create summaries table
CREATE_SUMMARIES_TABLE_SQL = """
CREATE TABLE content_creation.summaries (
    summary_id SERIAL PRIMARY KEY,
    transcript_id INTEGER NOT NULL REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    summary_text TEXT,
    model_used VARCHAR(100),
    generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""
CREATE_SUMMARIES_INDEX_TRANSCRIPT_SQL = """
CREATE INDEX IF NOT EXISTS idx_summaries_transcript_id ON content_creation.summaries(transcript_id);
"""
CREATE_SUMMARIES_INDEX_MEDIA_SQL = """
CREATE INDEX IF NOT EXISTS idx_summaries_media_id ON content_creation.summaries(media_id);
"""

# *** NEW: Create content_tags table ***
CREATE_CONTENT_TAGS_TABLE_SQL = """
CREATE TABLE content_creation.content_tags (
    tag_id SERIAL PRIMARY KEY,
    transcript_id INTEGER NOT NULL REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    tag_type VARCHAR(50) NOT NULL CHECK (tag_type IN ('keyword', 'topic', 'sentiment', 'action', 'entity')),
    tag_value VARCHAR(255) NOT NULL,
    model_used VARCHAR(100),
    score REAL CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    start_sec REAL,
    end_sec REAL,
    start_char INTEGER,
    end_char INTEGER,
    generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_valid_time_range CHECK (start_sec IS NULL OR end_sec IS NULL OR start_sec <= end_sec),
    CONSTRAINT chk_valid_char_range CHECK (start_char IS NULL OR end_char IS NULL OR start_char <= end_char)
);
"""
# *** NEW: Add indexes for content_tags table ***
CREATE_TAGS_INDEX_TRANSCRIPT_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_transcript_id ON content_creation.content_tags(transcript_id);
"""
CREATE_TAGS_INDEX_MEDIA_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_media_id ON content_creation.content_tags(media_id);
"""
CREATE_TAGS_INDEX_TYPE_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_type ON content_creation.content_tags(tag_type);
"""
CREATE_TAGS_INDEX_VALUE_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_value ON content_creation.content_tags(tag_value);
"""
CREATE_TAGS_INDEX_TYPE_VALUE_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_type_value ON content_creation.content_tags(tag_type, tag_value);
"""
CREATE_TAGS_INDEX_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_tags_time ON content_creation.content_tags(media_id, start_sec, end_sec) WHERE start_sec IS NOT NULL AND end_sec IS NOT NULL;
"""

# --- Main Execution Function ---

def setup_database():
    """Connects to PostgreSQL, drops/creates schema, creates tables using config."""
    conn = None
    cursor = None
    try:
        # Connect to the PostgreSQL server (connect to default 'postgres' db first)
        print(f"Connecting to PostgreSQL server at {config.DB_HOST}:{config.DB_PORT}...")
        conn = psycopg2.connect(
            dbname="postgres",
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        conn.autocommit = True
        cursor = conn.cursor()

        print(f"Checking if database '{config.DB_NAME}' exists...")
        cursor.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s"), (config.DB_NAME,))
        exists = cursor.fetchone()
        if not exists:
            print(f"Database '{config.DB_NAME}' does not exist. Creating...")
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.DB_NAME)))
            print(f"Database '{config.DB_NAME}' created.")
        else:
            print(f"Database '{config.DB_NAME}' already exists.")

        # Close initial connection and reconnect to the specific database
        print(f"Reconnecting to database '{config.DB_NAME}'...")
        cursor.close()
        conn.close()

        conn = psycopg2.connect(
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        cursor = conn.cursor()

        # --- Execute SQL Commands ---
        print("Executing database setup commands...")

        print("Dropping existing schema 'content_creation' (if exists)...")
        cursor.execute(DROP_SCHEMA_SQL)

        print("Creating schema 'content_creation'...")
        cursor.execute(CREATE_SCHEMA_SQL)

        print("Enabling pgvector extension...")
        cursor.execute(ENABLE_PGVECTOR_SQL)

        print("Creating table 'media'...")
        cursor.execute(CREATE_MEDIA_TABLE_SQL)

        print("Creating table 'scenes'...")
        cursor.execute(CREATE_SCENES_TABLE_SQL)

        print("Creating table 'transcripts'...")
        cursor.execute(CREATE_TRANSCRIPTS_TABLE_SQL)
        print("Creating index on 'transcripts'...")
        cursor.execute(CREATE_TRANSCRIPTS_INDEX_SQL)

        print("Creating table 'objects'...")
        cursor.execute(CREATE_OBJECTS_TABLE_SQL)

        print("Creating table 'faces'...")
        cursor.execute(CREATE_FACES_TABLE_SQL)

        print("Creating table 'embeddings'...")
        cursor.execute(CREATE_EMBEDDINGS_TABLE_SQL)
        print("Creating HNSW index on 'embeddings'...")
        cursor.execute(CREATE_EMBEDDINGS_INDEX_SQL)

        print("Creating table 'entities'...")
        cursor.execute(CREATE_ENTITIES_TABLE_SQL)
        print("Creating indexes on 'entities'...")
        cursor.execute(CREATE_ENTITIES_INDEX_SQL)
        cursor.execute(CREATE_ENTITIES_MEDIA_INDEX_SQL)

        print("Creating table 'summaries'...")
        cursor.execute(CREATE_SUMMARIES_TABLE_SQL)
        print("Creating indexes on 'summaries'...")
        cursor.execute(CREATE_SUMMARIES_INDEX_TRANSCRIPT_SQL)
        cursor.execute(CREATE_SUMMARIES_INDEX_MEDIA_SQL)

        # *** NEW: Create content_tags table and indexes ***
        print("Creating table 'content_tags'...")
        cursor.execute(CREATE_CONTENT_TAGS_TABLE_SQL)
        print("Creating indexes on 'content_tags'...")
        cursor.execute(CREATE_TAGS_INDEX_TRANSCRIPT_SQL)
        cursor.execute(CREATE_TAGS_INDEX_MEDIA_SQL)
        cursor.execute(CREATE_TAGS_INDEX_TYPE_SQL)
        cursor.execute(CREATE_TAGS_INDEX_VALUE_SQL)
        cursor.execute(CREATE_TAGS_INDEX_TYPE_VALUE_SQL)
        cursor.execute(CREATE_TAGS_INDEX_TIME_SQL)

        # Commit the changes for table/index creation
        conn.commit()
        print("Database setup completed successfully!")

    except (psycopg2.Error, ImportError, AttributeError) as e:
        print(f"Error during database setup: {e}")
        if conn:
            conn.rollback()
    finally:
        # Close cursor and connection
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("Database connection closed.")

# --- Run the Setup ---
if __name__ == "__main__":
    setup_database()