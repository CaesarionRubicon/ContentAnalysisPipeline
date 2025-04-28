import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from pathlib import Path
import json # Import the json module for serialization
# Remove: import ffmpeg
from pymediainfo import MediaInfo # Import MediaInfo

# --- Add Project Root to Python Path ---
# Ensures 'config' can be imported when running script from 'scripts' directory or root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config # Import settings from config/config.py

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

# --- Core Ingestion Functions ---

def register_media_file(source_path_str, media_type):
    """
    Registers a media file in the database if it doesn't exist.
    Extracts duration and metadata using pymediainfo and updates the record.
    """
    conn = get_db_connection()
    if not conn:
        return None # Connection failed

    source_path = Path(source_path_str)
    # Check if file exists before proceeding
    if not source_path.is_file():
        logging.error(f"Input file not found: {source_path_str}")
        return None

    source_uri = source_path.resolve().as_uri() # Use file URI as unique identifier
    filename = source_path.name

    media_id = None
    duration = None # Initialize duration
    media_info_data = {} # To store other metadata
    relevant_metadata_json = None # Initialize JSON variable

    # --- Extract Metadata using pymediainfo ---
    try:
        logging.debug(f"Parsing file with MediaInfo: {source_path_str}")
        # Point to the library path explicitly if needed, otherwise relies on PATH
        # Example: media_info = MediaInfo.parse(source_path_str, library_file='/path/to/mediainfo.dll')
        media_info = MediaInfo.parse(source_path_str)
        media_info_data = media_info.to_data() # Convert to dictionary

        # Extract duration (usually in milliseconds in general track)
        general_track = next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'General'), None)
        if general_track and 'duration' in general_track:
            # Handle potential None or empty string for duration
            duration_str = general_track['duration']
            if duration_str:
                try:
                    duration_ms = float(duration_str)
                    duration = duration_ms / 1000.0 # Convert ms to seconds
                    logging.info(f"Extracted duration for {filename}: {duration:.2f} seconds")
                except (ValueError, TypeError):
                     logging.warning(f"Could not parse duration value '{duration_str}' for {filename}")
                     duration = 0.0
            else:
                 logging.warning(f"Duration field empty in General track for {filename}")
                 duration = 0.0
        else:
             logging.warning(f"Could not find duration in General track for {filename}")
             duration = 0.0 # Default if not found

        # Prepare metadata to potentially store (convert raw dict to JSON string)
        # Be selective about what you store to avoid huge JSON blobs
        if media_info_data:
             try:
                 # Example: Store only general, video, and first audio track info
                 relevant_data = {
                     'general': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'General'), None),
                     'video': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'Video'), None),
                     'audio': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'Audio'), None) # Just the first audio
                 }
                 relevant_metadata_json = json.dumps({k: v for k, v in relevant_data.items() if v}, indent=2) # Store non-empty tracks, pretty print
             except Exception as json_e:
                 logging.error(f"Failed to serialize metadata to JSON for {filename}: {json_e}")

    except FileNotFoundError:
         logging.error(f"MediaInfo library (mediainfo.dll or equivalent) not found or accessible in system PATH.")
         logging.error("Please install MediaInfo from https://mediaarea.net/en/MediaInfo/Download")
         # Close DB connection if opened
         if conn: conn.close()
         return None # Cannot proceed without MediaInfo library
    except Exception as e:
        logging.error(f"Error parsing file {filename} with MediaInfo: {e}")
        # Optionally try to proceed without duration/metadata or just fail
        duration = 0.0 # Set default duration on error


    # --- Interact with Database ---
    try:
        with conn.cursor() as cur:
            # Check if media already exists
            cur.execute(
                sql.SQL("SELECT id, duration FROM content_creation.media WHERE source_uri = %s"),
                (source_uri,)
            )
            result = cur.fetchone()

            if result:
                media_id = result[0]
                existing_duration = result[1]
                logging.info(f"Media already registered for {source_uri}. DB ID: {media_id}")

                # Determine if update is needed (missing duration or metadata, or different duration)
                needs_update = False
                if existing_duration is None or abs(existing_duration - duration) > 0.1:
                    needs_update = True
                # Add check for metadata later if desired (e.g., cur.execute to get existing metadata)

                if needs_update:
                    logging.info(f"Updating duration/metadata for media ID {media_id}.")
                    cur.execute(
                        sql.SQL("""
                            UPDATE content_creation.media
                            SET duration = %s, status = %s, metadata = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s;
                        """),
                        (duration, 'metadata_extracted', relevant_metadata_json, media_id) # Add metadata JSON
                    )
                    conn.commit()
                else:
                    logging.info(f"Duration for media ID {media_id} is already up-to-date.")
                    # Optionally update status if it wasn't already 'metadata_extracted'
                    cur.execute(
                        sql.SQL("""
                            UPDATE content_creation.media SET status = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s AND status != %s;
                        """),
                        ('metadata_extracted', media_id, 'metadata_extracted')
                    )
                    conn.commit()


            else:
                logging.info(f"Registering new media: {filename} ({source_uri})")
                # Insert new media record with duration, status, and metadata
                cur.execute(
                    sql.SQL("""
                        INSERT INTO content_creation.media
                            (filename, source_uri, media_type, duration, status, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id;
                    """),
                    (filename, source_uri, media_type, duration, 'metadata_extracted', relevant_metadata_json) # Add metadata
                )
                media_id = cur.fetchone()[0]
                conn.commit() # Commit the insert
                logging.info(f"Successfully registered {filename}. DB ID: {media_id}")

    except psycopg2.Error as e:
        logging.error(f"Database error during media registration/update for {filename}: {e}")
        if conn: conn.rollback() # Rollback on error
        media_id = None # Ensure media_id is None on error
    except Exception as e: # Catch other potential errors (like DB connection closed unexpectedly)
         logging.error(f"Unexpected error during DB interaction for {filename}: {e}")
         media_id = None
    finally:
        if conn and not conn.closed:
            conn.close()
            logging.debug("Database connection closed for register_media_file.")

    return media_id


def process_single_file(file_path_str):
    """Processes a single media file: registers it and extracts metadata."""
    logging.info(f"Processing file: {file_path_str}")
    file_path = Path(file_path_str)

    # Basic type detection based on extension (can be improved)
    extension = file_path.suffix.lower()
    media_type = 'unknown'
    if extension in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']: # Added more video types
        media_type = 'video'
    elif extension in ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac']: # Added more audio types
        media_type = 'audio'
    elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']: # Added more image types
         media_type = 'image'
         logging.warning(f"Image file type '{extension}' detected. Metadata extraction might be limited by MediaInfo.")
    # Add other types if needed

    if media_type == 'unknown':
        logging.warning(f"Skipping file with unknown/unsupported media type extension: {extension} ({file_path.name})")
        return # Skip unknown types

    media_id = register_media_file(str(file_path), media_type) # Pass full path string

    if media_id:
        logging.info(f"Successfully processed/registered file {file_path.name}. Media ID: {media_id}")
        # Future steps for this file (transcript ingestion, etc.) would go here or be triggered
    else:
        logging.error(f"Failed to process/register file {file_path.name}.")


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest media files into the database and extract metadata.")
    parser.add_argument("-f", "--file", type=str, help="Path to a single media file to ingest.")
    parser.add_argument("-d", "--directory", type=str, help="Path to a directory of media files to ingest.")
    # Add more arguments as needed (e.g., --media-type, --youtube-url)

    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        # Check existence within process_single_file now
        process_single_file(str(file_path))

    elif args.directory:
        dir_path = Path(args.directory)
        if dir_path.is_dir():
            logging.info(f"Scanning directory: {args.directory}")
            count = 0
            for item in dir_path.iterdir():
                # Make sure it's a file before processing
                if item.is_file():
                    process_single_file(str(item)) # Process each file found
                    count += 1
            logging.info(f"Finished scanning directory. Processed {count} potential files.")
        else:
            logging.error(f"Provided directory path does not exist or is not a directory: {args.directory}")
    else:
        logging.warning("No input specified. Use --file or --directory.")
        parser.print_help()

    logging.info("--- Ingestion Script Finished ---")