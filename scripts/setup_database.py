import os
import psycopg2
from psycopg2 import sql
# Remove: from dotenv import load_dotenv (Handled by config.py)
import sys # Used for path modification

# --- Add Project Root to Python Path ---
# This helps Python find the 'config' module when running scripts from the 'scripts' directory
from config import config # Import the config module from the config directory

# --- SQL Commands (Remain the Same) ---

# Drop existing schema and tables if they exist (for a clean reset)
# Use CASCADE to drop objects that depend on the schema/tables
DROP_SCHEMA_SQL = """
DROP SCHEMA IF EXISTS content_creation CASCADE;
"""

# Create the schema
CREATE_SCHEMA_SQL = """
CREATE SCHEMA content_creation;
"""

# Create the media table (renamed from videos, added media_type, source_uri, status)
CREATE_MEDIA_TABLE_SQL = """
CREATE TABLE content_creation.media (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    source_uri VARCHAR(1024) NOT NULL UNIQUE, -- Path or URL, must be unique
    media_type VARCHAR(20) NOT NULL, -- 'video', 'audio', 'image'
    title VARCHAR(255),
    duration REAL, -- Duration in seconds (float)
    status VARCHAR(50) DEFAULT 'pending', -- e.g., pending, processing, completed, error
    error_message TEXT,
    metadata JSONB, -- Store other metadata like resolution, frame rate, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the scenes table (referencing media table)
CREATE_SCENES_TABLE_SQL = """
CREATE TABLE content_creation.scenes (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the transcripts table (referencing media table)
CREATE_TRANSCRIPTS_TABLE_SQL = """
CREATE TABLE content_creation.transcripts (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL, -- Can be NULL if transcript applies to whole media
    end_sec REAL,   -- Can be NULL
    text TEXT NOT NULL,
    confidence REAL, -- Optional confidence score from STT
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""
# Add index for faster lookup by media_id and time
CREATE_TRANSCRIPTS_INDEX_SQL = """
CREATE INDEX idx_transcripts_media_time ON content_creation.transcripts (media_id, start_sec, end_sec);
"""

# Create the objects table (referencing media table) - Schema example
CREATE_OBJECTS_TABLE_SQL = """
CREATE TABLE content_creation.objects (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    label VARCHAR(255) NOT NULL,
    confidence REAL,
    bounding_box JSONB, -- Store coordinates if available
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Create the faces table (referencing media table) - Schema example
CREATE_FACES_TABLE_SQL = """
CREATE TABLE content_creation.faces (
    id SERIAL PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    face_id VARCHAR(255), -- ID assigned by detection/recognition system
    confidence REAL,
    bounding_box JSONB,
    embedding BYTEA, -- Placeholder for potential face embeddings (vector)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Enable the pgvector extension (if not already enabled in the database)
ENABLE_PGVECTOR_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
"""

# Create the embeddings table (referencing media OR potentially scenes/transcripts)
# Storing embeddings for transcript segments might be common
CREATE_EMBEDDINGS_TABLE_SQL = """
CREATE TABLE content_creation.embeddings (
    id SERIAL PRIMARY KEY,
    media_id INTEGER REFERENCES content_creation.media(id) ON DELETE CASCADE,
    transcript_id INTEGER REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    -- Add scene_id if embedding scenes: scene_id INTEGER REFERENCES content_creation.scenes(id) ON DELETE CASCADE,
    description TEXT, -- e.g., "Transcript segment", "Scene description"
    model_name VARCHAR(100), -- e.g., 'all-MiniLM-L6-v2'
    embedding VECTOR(384) NOT NULL, -- Use config.EMBEDDING_DIMENSION if defined, else hardcode
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Ensure at least one foreign key is linked
    CONSTRAINT chk_embedding_source CHECK (media_id IS NOT NULL OR transcript_id IS NOT NULL ) -- Add OR scene_id IS NOT NULL if embedding scenes
);
"""
# Add index for faster vector similarity search (using HNSW index here)
# Adjust parameters based on your data size and performance needs
CREATE_EMBEDDINGS_INDEX_SQL = """
CREATE INDEX ON content_creation.embeddings USING hnsw (embedding vector_cosine_ops);
"""

# Create the entities table (linking to transcripts)
CREATE_ENTITIES_TABLE_SQL = """
CREATE TABLE content_creation.entities (
    id SERIAL PRIMARY KEY,
    transcript_id INTEGER NOT NULL REFERENCES content_creation.transcripts(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES content_creation.media(id) ON DELETE CASCADE,
    text TEXT NOT NULL,         -- The actual entity text (e.g., "Steve Jobs")
    label VARCHAR(50) NOT NULL, -- The entity type (e.g., "PERSON", "ORG", "GPE")
    start_char INTEGER NOT NULL, -- Start character offset in transcript text
    end_char INTEGER NOT NULL,   -- End character offset in transcript text
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    -- Add UNIQUE constraint? Maybe not, same entity could appear multiple times
);
"""
# Add index for faster lookup by transcript_id or label
CREATE_ENTITIES_INDEX_SQL = """
CREATE INDEX idx_entities_transcript_label ON content_creation.entities (transcript_id, label);
"""
CREATE_ENTITIES_MEDIA_INDEX_SQL = """
CREATE INDEX idx_entities_media_label ON content_creation.entities (media_id, label);
"""

# --- Main Execution Function ---

def setup_database():
    """Connects to PostgreSQL, drops/creates schema, creates tables using config."""
    conn = None
    cursor = None
    try:
        # Connect to the PostgreSQL server (connect to default 'postgres' db first)
        # Use values from config module
        print(f"Connecting to PostgreSQL server at {config.DB_HOST}:{config.DB_PORT}...")
        conn = psycopg2.connect(
            dbname="postgres", # Connect to default db to manage other dbs/extensions
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        conn.autocommit = True # Autocommit for DDL commands like CREATE/DROP DATABASE/EXTENSION
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
            dbname=config.DB_NAME, # Use config value here
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
        cursor.execute(ENABLE_PGVECTOR_SQL) # Needs to be run before creating tables with VECTOR type

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

        # Commit the changes for table/index creation
        conn.commit()
        print("Database setup completed successfully!")

    except (psycopg2.Error, ImportError, AttributeError) as e: # Catch potential config import errors too
        print(f"Error during database setup: {e}")
        # Rollback in case of error during table creation
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
    # This ensures the setup runs only when the script is executed directly
    setup_database()