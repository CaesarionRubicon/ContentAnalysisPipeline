import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from pathlib import Path
import json # Import the json module for serialization
from pymediainfo import MediaInfo # Import MediaInfo
import pysrt # Import pysrt for SRT parsing
import whisper # Import Whisper

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
        logging.FileHandler(log_file, encoding='utf-8'), # Specify UTF-8 for log file
        logging.StreamHandler()        # Log to console
    ]
)
# Initial message now moved to main execution block

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
        logging.debug(f"Database connection established to {config.DB_NAME}@{config.DB_HOST}") # Use debug level
        return conn
    except psycopg2.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

# --- Core Ingestion Functions ---

def register_media_file(source_path_str, media_type):
    """
    Registers a media file in the database if it doesn't exist.
    Extracts duration and metadata using pymediainfo and updates the record.
    Returns the media_id or None if an error occurs.
    """
    conn = get_db_connection()
    if not conn:
        return None # Connection failed

    source_path = Path(source_path_str)
    if not source_path.is_file():
        logging.error(f"Input file not found: {source_path_str}")
        return None

    source_uri = source_path.resolve().as_uri()
    filename = source_path.name

    media_id = None
    duration = None
    media_info_data = {}
    relevant_metadata_json = None

    # Extract Metadata using pymediainfo
    try:
        logging.debug(f"Parsing file with MediaInfo: {source_path_str}")
        media_info = MediaInfo.parse(source_path_str)
        media_info_data = media_info.to_data()

        general_track = next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'General'), None)
        if general_track and 'duration' in general_track:
            duration_str = general_track['duration']
            if duration_str:
                try:
                    duration_ms = float(duration_str)
                    duration = duration_ms / 1000.0
                    logging.info(f"Extracted duration for {filename}: {duration:.2f} seconds")
                except (ValueError, TypeError):
                     logging.warning(f"Could not parse duration value '{duration_str}' for {filename}")
                     duration = 0.0
            else:
                 logging.warning(f"Duration field empty in General track for {filename}")
                 duration = 0.0
        else:
             logging.warning(f"Could not find duration in General track for {filename}")
             duration = 0.0

        if media_info_data:
             try:
                 relevant_data = {
                     'general': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'General'), None),
                     'video': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'Video'), None),
                     'audio': next((t for t in media_info_data.get('tracks', []) if t['track_type'] == 'Audio'), None)
                 }
                 relevant_metadata_json = json.dumps({k: v for k, v in relevant_data.items() if v}, indent=2)
             except Exception as json_e:
                 logging.error(f"Failed to serialize metadata to JSON for {filename}: {json_e}")

    except FileNotFoundError:
         logging.error(f"MediaInfo library (mediainfo.dll or equivalent) not found or accessible in system PATH.")
         if conn: conn.close()
         return None
    except Exception as e:
        logging.error(f"Error parsing file {filename} with MediaInfo: {e}")
        duration = 0.0

    # Interact with Database
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT id, duration FROM content_creation.media WHERE source_uri = %s"),
                (source_uri,)
            )
            result = cur.fetchone()

            if result:
                media_id = result[0]
                existing_duration = result[1]
                logging.info(f"Media already registered for {source_uri}. DB ID: {media_id}")
                needs_update = False
                if existing_duration is None or abs((existing_duration or 0.0) - duration) > 0.1:
                    needs_update = True

                if needs_update:
                    logging.info(f"Updating duration/metadata for media ID {media_id}.")
                    cur.execute(
                        sql.SQL("""
                            UPDATE content_creation.media
                            SET duration = %s, status = %s, metadata = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s;
                        """),
                        (duration, 'metadata_extracted', relevant_metadata_json, media_id)
                    )
                    conn.commit()
                else:
                    logging.info(f"Duration for media ID {media_id} is already up-to-date.")
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
                cur.execute(
                    sql.SQL("""
                        INSERT INTO content_creation.media
                            (filename, source_uri, media_type, duration, status, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id;
                    """),
                    (filename, source_uri, media_type, duration, 'metadata_extracted', relevant_metadata_json)
                )
                media_id = cur.fetchone()[0]
                conn.commit()
                logging.info(f"Successfully registered {filename}. DB ID: {media_id}")

    except psycopg2.Error as e:
        logging.error(f"Database error during media registration/update for {filename}: {e}")
        if conn: conn.rollback()
        media_id = None
    except Exception as e:
         logging.error(f"Unexpected error during DB interaction for {filename}: {e}")
         media_id = None
    finally:
        if conn and not conn.closed:
            conn.close()
            logging.debug("Database connection closed for register_media_file.")
    return media_id

# <<< --- WHISPER FUNCTION DEFINITION --- >>>
def transcribe_with_whisper(media_path_str, output_dir):
    """Transcribes a media file using Whisper and saves as SRT."""
    media_path = Path(media_path_str)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True) # Ensure output dir exists

    srt_filename = media_path.stem + ".srt"
    srt_path = output_path / srt_filename
    transcript_exists = srt_path.is_file()

    if transcript_exists:
        logging.info(f"Transcription file already exists: {srt_path}. Skipping Whisper.")
        return str(srt_path) # Return path to existing file

    logging.info(f"Starting Whisper transcription for: {media_path.name}")
    try:
        # Load the model
        model_size = "base.en" # <<< CHOOSE MODEL SIZE HERE
        logging.info(f"Loading Whisper model: {model_size}")
        model = whisper.load_model(model_size)

        # Run transcription
        logging.info(f"Transcribing {media_path.name} with fp16=True (this may take a while)...")
        result = model.transcribe(media_path_str, fp16=True, verbose=True) # <<< USE FP16=TRUE HERE

        # Use whisper's built-in SRT writer utility
        from whisper.utils import WriteSRT # Import here to avoid loading if not needed

        logging.info(f"Writing transcription to SRT file: {srt_path}")
        writer = WriteSRT(output_dir=str(output_path))
        writer(result, media_path.stem) # Pass stem, writer adds .srt

        if srt_path.is_file():
             logging.info(f"Whisper transcription completed successfully. Output: {srt_path}")
             return str(srt_path)
        else:
             logging.error(f"Whisper transcription ran but SRT file was not created at {srt_path}")
             return None

    except Exception as e:
        logging.error(f"Error during Whisper transcription for {media_path.name}: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            logging.error(f"Whisper/ffmpeg stderr: {e.stderr.decode()}")
        return None
# <<< --- END WHISPER FUNCTION --- >>>

def ingest_transcript_file(media_id, transcript_path):
    """Reads an SRT file and inserts segments into the transcripts table."""
    conn = get_db_connection()
    if not conn:
        logging.error(f"Cannot connect to DB to ingest transcript: {transcript_path.name}")
        return False

    logging.info(f"Ingesting transcript for media ID {media_id} from {transcript_path.name}")
    success = False
    try:
        encodings_to_try = ['utf-8', 'iso-8859-1', 'windows-1252']
        subs = None
        for enc in encodings_to_try:
            try:
                 subs = pysrt.open(str(transcript_path), encoding=enc)
                 logging.info(f"Successfully opened transcript with encoding: {enc}")
                 break
            except UnicodeDecodeError:
                 logging.warning(f"Failed to decode transcript with encoding: {enc}")
            except FileNotFoundError:
                 logging.error(f"Transcript file not found during open attempt: {transcript_path}")
                 raise
            except Exception as e_open:
                 logging.error(f"Error opening SRT file {transcript_path.name} with encoding {enc}: {e_open}")

        if subs is None:
            logging.error(f"Could not open/decode transcript file {transcript_path.name} with any attempted encoding.")
            raise IOError("Failed to decode transcript file")

        logging.info(f"Parsed {len(subs)} subtitle segments from {transcript_path.name}")

        with conn.cursor() as cur:
            logging.info(f"Deleting existing transcript segments for media ID {media_id} before insertion.")
            cur.execute("DELETE FROM content_creation.transcripts WHERE media_id = %s", (media_id,))

            insert_count = 0
            for sub in subs:
                start_sec = sub.start.ordinal / 1000.0
                end_sec = sub.end.ordinal / 1000.0
                text = sub.text_without_tags

                if not text.strip(): continue

                cur.execute(
                    sql.SQL("""
                        INSERT INTO content_creation.transcripts
                            (media_id, start_sec, end_sec, text)
                        VALUES (%s, %s, %s, %s);
                    """),
                    (media_id, start_sec, end_sec, text)
                )
                insert_count += 1

            conn.commit()
            logging.info(f"Successfully inserted {insert_count} transcript segments for media ID {media_id}.")
            success = True

    except FileNotFoundError:
        logging.error(f"Transcript file not found: {transcript_path}")
    except (pysrt.Error, IOError) as e:
        logging.error(f"Error parsing/reading SRT file {transcript_path.name}: {e}")
    except psycopg2.Error as e:
        logging.error(f"Database error inserting transcripts for media ID {media_id}: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.error(f"Unexpected error ingesting transcript {transcript_path.name}: {e}")
        if conn: conn.rollback()
    finally:
        if conn and not conn.closed:
            conn.close()
            logging.debug("Database connection closed for ingest_transcript_file.")
    return success

def process_single_file(file_path_str):
    """Processes a single media file: registers it, extracts metadata, and ingests transcript."""
    logging.info(f"Processing file: {file_path_str}")
    file_path = Path(file_path_str)

    extension = file_path.suffix.lower()
    media_type = 'unknown'
    if extension in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']:
        media_type = 'video'
    elif extension in ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac']:
        media_type = 'audio'
    elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
         media_type = 'image'
         logging.warning(f"Image file type '{extension}' detected. Transcript ingestion will be skipped.")

    if media_type == 'unknown':
        logging.warning(f"Skipping file with unknown/unsupported media type extension: {extension} ({file_path.name})")
        return

    media_id = register_media_file(str(file_path), media_type)

    if media_id and media_type in ['video', 'audio']:
        logging.info(f"Successfully processed/registered file {file_path.name}. Media ID: {media_id}")

        transcript_filename_srt = file_path.stem + ".srt"
        transcript_path_srt = config.RAW_TRANSCRIPTS_DIR / transcript_filename_srt
        transcript_to_ingest = None

        logging.info(f"Checking for existing transcript: {transcript_path_srt}")
        if transcript_path_srt.is_file():
            logging.info(f"Found existing transcript file.")
            transcript_to_ingest = str(transcript_path_srt)
        else:
            logging.info(f"No existing SRT found. Attempting transcription with Whisper...")
            # Run Whisper - output directly to the target transcripts directory
            generated_srt_path = transcribe_with_whisper(str(file_path), str(config.RAW_TRANSCRIPTS_DIR))
            if generated_srt_path:
                transcript_to_ingest = generated_srt_path
            else:
                logging.error(f"Whisper transcription failed for {file_path.name}.")

        if transcript_to_ingest:
            ingest_transcript_file(media_id, Path(transcript_to_ingest))
        else:
            logging.warning(f"No transcript available to ingest for media ID {media_id}.")

    elif media_id:
        logging.info(f"Successfully processed/registered file {file_path.name}. Media ID: {media_id}. Skipping transcript check for media type '{media_type}'.")
    else:
        logging.error(f"Failed to process/register file {file_path.name}. Skipping transcript processing.")

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Ingestion Script ---") # Moved initial message here
    parser = argparse.ArgumentParser(description="Ingest media files into the database, extract metadata, and ingest associated transcripts.")
    parser.add_argument("-f", "--file", type=str, help="Path to a single media file to ingest.")
    parser.add_argument("-d", "--directory", type=str, help="Path to a directory of media files to ingest.")

    args = parser.parse_args()

    if args.file:
        process_single_file(args.file)

    elif args.directory:
        dir_path = Path(args.directory)
        if dir_path.is_dir():
            logging.info(f"Scanning directory: {args.directory}")
            count = 0
            for item in dir_path.iterdir():
                if item.is_file():
                    process_single_file(str(item))
                    count += 1
            logging.info(f"Finished scanning directory. Processed {count} potential files.")
        else:
            logging.error(f"Provided directory path does not exist or is not a directory: {args.directory}")
    else:
        logging.warning("No input specified. Use --file or --directory.")
        parser.print_help()

    logging.info("--- Ingestion Script Finished ---")