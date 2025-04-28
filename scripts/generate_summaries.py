import logging
import sys
import os
from openai import OpenAI  # Import the OpenAI library

# --- Add Project Root to Python Path ---
# Assuming the script is in D:\ContentAnalysisPipeline\scripts
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from config import config  # Import config after adjusting sys.path
from scripts.db_utils import get_db_connection, close_db_connection

# --- Constants ---
LOG_FILE = config.LOGS_DIR / "summary_generation.log"
TRANSCRIPT_STATUS_PENDING = 'entities_extracted'  # Status to query for
TRANSCRIPT_STATUS_SUCCESS = 'summarized'  # Status to set after success
TRANSCRIPT_STATUS_FAILED = 'summary_failed'  # Status to set on failure
OPENAI_MODEL = "gpt-4o-mini"  # Updated to use GPT-4o Mini

# --- Logging Setup ---
# Ensure logs directory exists
config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)  # Also print logs to console
    ]
)

# --- OpenAI Client Initialization ---
# Ensure API key is loaded via config (which loads .env)
if not config.OPENAI_API_KEY:
    logging.error("OpenAI API key not found in environment variables/config.")
    sys.exit(1)  # Exit if key is missing

try:
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    logging.info("OpenAI client initialized.")
except Exception as e:
    logging.error(f"Failed to initialize OpenAI client: {e}")
    sys.exit(1)

# --- Core Functions ---

def get_transcripts_to_summarize(conn):
    """Fetches transcripts that need summarization."""
    sql = """
        SELECT id, media_id, text
        FROM content_creation.transcripts
        WHERE status = %s
        ORDER BY created_at
        LIMIT 1; -- Process only one transcript
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (TRANSCRIPT_STATUS_PENDING,))
            transcripts = cursor.fetchall()
            logging.info(f"Found {len(transcripts)} transcripts with status '{TRANSCRIPT_STATUS_PENDING}'.")
            return transcripts
    except Exception as e:
        logging.error(f"Error fetching transcripts to summarize: {e}")
        return []

def generate_summary_with_openai(transcript_text):
    """Generates a summary using the OpenAI API."""
    logging.debug(f"Attempting to summarize text (first 100 chars): {transcript_text[:100]}...")
    try:
        # --- Basic Prompt ---
        # You can refine this prompt significantly for better results
        system_prompt = "You are a helpful assistant designed to summarize video transcripts concisely."
        user_prompt = f"Please provide a brief summary (2-3 sentences) of the following transcript:\n\n{transcript_text}"

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,  # Adjust for creativity vs factualness
            max_tokens=150  # Adjust based on desired summary length
            # Add other parameters as needed (e.g., top_p)
        )
        summary = response.choices[0].message.content.strip()
        logging.debug(f"Successfully generated summary: {summary[:100]}...")
        return summary
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None

def save_summary_and_update_status(conn, transcript_id, media_id, summary_text, new_status):
    """Saves the summary and updates the transcript status in a transaction."""
    summary_sql = """
        INSERT INTO content_creation.summaries (transcript_id, media_id, summary_text, model_used)
        VALUES (%s, %s, %s, %s);
    """
    update_sql = """
        UPDATE content_creation.transcripts
        SET status = %s
        WHERE id = %s;
    """
    try:
        with conn.cursor() as cursor:
            # Insert the summary
            cursor.execute(summary_sql, (transcript_id, media_id, summary_text, OPENAI_MODEL))
            logging.debug(f"Inserted summary for transcript_id {transcript_id}.")

            # Update the transcript status
            cursor.execute(update_sql, (new_status, transcript_id))
            logging.debug(f"Updated status for transcript_id {transcript_id} to '{new_status}'.")

        # Commit the transaction if both operations were successful
        conn.commit()
        logging.info(f"Successfully saved summary and updated status for transcript_id {transcript_id}.")
        return True
    except Exception as e:
        logging.error(f"Database error saving summary/updating status for transcript_id {transcript_id}: {e}")
        conn.rollback()  # Rollback transaction on error
        return False

def update_transcript_status(conn, transcript_id, status):
    """Updates only the transcript status (e.g., on failure)."""
    sql = """
        UPDATE content_creation.transcripts
        SET status = %s
        WHERE id = %s;
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (status, transcript_id))
        conn.commit()  # Commit this status update
        logging.warning(f"Updated status for transcript_id {transcript_id} to '{status}' (likely due to failure).")
    except Exception as e:
        logging.error(f"Failed to update transcript status to '{status}' for id {transcript_id}: {e}")
        conn.rollback()

# --- Main Orchestration Function ---

def main():
    """Main function to generate summaries."""
    logging.info("Starting summary generation process...")
    conn = get_db_connection()
    if not conn:
        logging.error("Could not establish database connection. Exiting.")
        return  # Exit if no connection

    processed_count = 0
    failed_count = 0
    try:
        transcripts_to_process = get_transcripts_to_summarize(conn)

        if not transcripts_to_process:
            logging.info("No transcripts found needing summarization.")
            return  # Exit cleanly if nothing to do

        for transcript_id, media_id, transcript_text in transcripts_to_process:
            logging.info(f"Processing transcript_id: {transcript_id}")

            if not transcript_text or transcript_text.isspace():
                logging.warning(f"Skipping transcript_id {transcript_id}: Text is empty or whitespace.")
                update_transcript_status(conn, transcript_id, TRANSCRIPT_STATUS_FAILED)
                failed_count += 1
                continue

            # Generate summary
            summary = generate_summary_with_openai(transcript_text)

            if summary:
                # Save summary and update status
                if save_summary_and_update_status(conn, transcript_id, media_id, summary, TRANSCRIPT_STATUS_SUCCESS):
                    processed_count += 1
                else:
                    # save_summary function handles logging and rollback
                    failed_count += 1
                    # Status remains 'entities_extracted' or whatever it was before tx failed
            else:
                # Failed to generate summary (OpenAI call failed)
                logging.error(f"Failed to generate summary for transcript_id {transcript_id}.")
                update_transcript_status(conn, transcript_id, TRANSCRIPT_STATUS_FAILED)
                failed_count += 1

    except Exception as e:
        logging.exception(f"An unexpected error occurred during the main loop: {e}")
        # Attempt to rollback any pending transaction, although it might be too late
        if conn: conn.rollback()
    finally:
        close_db_connection(conn)
        logging.info(f"Summary generation process finished. Processed: {processed_count}, Failed: {failed_count}.")

# --- Script Execution ---
if __name__ == "__main__":
    # Load configuration explicitly if needed (already done by importing config)
    # config.load_config()  # Ensure latest config is loaded if script runs long

    main()