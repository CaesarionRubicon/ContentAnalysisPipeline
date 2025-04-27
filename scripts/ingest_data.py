import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from pathlib import Path

# --- Add Project Root to Python Path ---
# Ensures 'config' can be imported when running script from 'scripts' directory or root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

import config # Import settings from config/config.py

# --- Logging Setup ---
# Set up basic logging to file and console
log_file = config.LOGS_DIR / 'ingestion.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file), # Log to file
        logging.StreamHandler()        # Log to console
    ]
)
logging.info("--- Starting Ingestion Script ---")

# --- Database Connection Function ---
def get_db_connection():
    """Establishes and returns a database connection using config."""
    try:
        conn = psycopg2.connect(
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        logging.info(f"Database connection established to {config.DB_NAME}@{config.DB_HOST}")
        return conn
    except psycopg2.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

# --- Core Ingestion Functions (Placeholders) ---

def register_media_file(source_path_str, media_type):
    """Registers a media file in the database if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        return None # Connection failed

    source_path = Path(source_path_str)
    source_uri = source_path.resolve().as_uri() # Use file URI as unique identifier
    filename = source_path.name

    media_id = None # Initialize media_id

    try:
        with conn.cursor() as cur:
            # Check if media already exists (idempotency)
            cur.execute(
                sql.SQL("SELECT id FROM content_creation.media WHERE source_uri = %s"),
                (source_uri,)
            )
            result = cur.fetchone()

            if result:
                media_id = result[0]
                logging.info(f"Media already registered for {source_uri}. DB ID: {media_id}")
                # Optional: Update status or check if re-processing is needed? For now, just return existing ID.
            else:
                logging.info(f"Registering new media: {filename} ({source_uri})")
                # Insert new media record
                cur.execute(
                    sql.SQL("""
                        INSERT INTO content_creation.media (filename, source_uri, media_type, status)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id;
                    """),
                    (filename, source_uri, media_type, 'pending') # Initial status
                )
                media_id = cur.fetchone()[0]
                conn.commit() # Commit the insert
                logging.info(f"Successfully registered {filename}. DB ID: {media_id}")

    except psycopg2.Error as e:
        logging.error(f"Database error during media registration for {filename}: {e}")
        conn.rollback() # Rollback on error
        media_id = None # Ensure media_id is None on error
    finally:
        if conn:
            conn.close()
            logging.debug("Database connection closed for register_media_file.") # Use debug level for less critical info

    return media_id


def process_single_file(file_path_str):
    """Processes a single media file: registers it."""
    logging.info(f"Processing file: {file_path_str}")
    # Basic type detection based on extension (can be improved)
    extension = Path(file_path_str).suffix.lower()
    media_type = 'unknown'
    if extension in ['.mp4', '.mov', '.avi', '.mkv']:
        media_type = 'video'
    elif extension in ['.mp3', '.wav', '.m4a', '.aac']:
        media_type = 'audio'
    elif extension in ['.jpg', '.jpeg', '.png', '.gif']:
         media_type = 'image'
    else:
        logging.warning(f"Unknown media type for extension: {extension}")
        return # Skip unknown types for now

    media_id = register_media_file(file_path_str, media_type)

    if media_id:
        logging.info(f"Successfully processed/registered file {file_path_str}. Media ID: {media_id}")
        # Future steps for this file (metadata extraction, transcript ingestion) would go here
    else:
        logging.error(f"Failed to process/register file {file_path_str}.")


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest media files into the database.")
    parser.add_argument("-f", "--file", type=str, help="Path to a single media file to ingest.")
    parser.add_argument("-d", "--directory", type=str, help="Path to a directory of media files to ingest.")
    # Add more arguments as needed (e.g., --media-type, --youtube-url)

    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        if file_path.is_file():
            process_single_file(str(file_path))
        else:
            logging.error(f"Provided file path does not exist or is not a file: {args.file}")
    elif args.directory:
        dir_path = Path(args.directory)
        if dir_path.is_dir():
            logging.info(f"Scanning directory: {args.directory}")
            for item in dir_path.iterdir():
                if item.is_file():
                    process_single_file(str(item)) # Process each file found
                # Optional: Add recursive scanning?
        else:
            logging.error(f"Provided directory path does not exist or is not a directory: {args.directory}")
    else:
        logging.warning("No input specified. Use --file or --directory.")
        parser.print_help()

    logging.info("--- Ingestion Script Finished ---")