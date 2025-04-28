import logging
import sys
import os
import torch # Transformers often requires torch
from transformers import pipeline # Import the pipeline helper

# --- Add Project Root to Python Path ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from config import config
from scripts.db_utils import get_db_connection, close_db_connection

# --- Constants ---
LOG_FILE = config.LOGS_DIR / "tag_generation.log"
TRANSCRIPT_STATUS_PENDING = 'summarized'         # Status to query for (after summarization)
TRANSCRIPT_STATUS_SUCCESS = 'tags_generated'     # Status to set after success
TRANSCRIPT_STATUS_FAILED = 'tagging_failed'      # Status to set on failure

# --- Model Configuration ---
# Using Zero-Shot Classification for flexible topic/keyword tagging
# You can change the model name if desired. Consider memory/performance.
# facebook/bart-large-mnli is a popular choice. moritzvolz/bart-large-mnli-facebook-onnx is optimized but might need onnxruntime. Let's stick to the standard one first.
CLASSIFICATION_MODEL = "facebook/bart-large-mnli"
# Define candidate labels (topics/keywords) you want to check for.
# This list can be expanded or changed based on your content.
CANDIDATE_LABELS = [
    'technology', 'software', 'hardware', 'AI', 'machine learning',
    'business', 'finance', 'economics', 'stocks',
    'politics', 'government', 'election',
    'sports', 'basketball', 'football', 'gaming',
    'entertainment', 'music', 'film', 'celebrity', 'interview',
    'science', 'health', 'medicine', 'space',
    'lifestyle', 'food', 'travel', 'art', 'culture',
    'news', 'world affairs', 'documentary', 'commentary',
    'product review', 'tutorial', 'education',
    'positive sentiment', 'negative sentiment', 'neutral sentiment' # Example sentiment tags
    # Add more specific keywords or topics relevant to your library
]
SCORE_THRESHOLD = 0.70 # Minimum confidence score to accept a tag (adjust as needed)

# --- Logging Setup ---
config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- Hugging Face Pipeline Initialization ---
try:
    # Check for GPU availability
    device = 0 if torch.cuda.is_available() else -1 # Use GPU 0 if available, else CPU
    logging.info(f"Initializing Hugging Face pipeline for zero-shot-classification on device: {'GPU' if device == 0 else 'CPU'}")
    # Initialize the zero-shot classifier pipeline
    classifier = pipeline("zero-shot-classification",
                          model=CLASSIFICATION_MODEL,
                          device=device)
    logging.info(f"Zero-shot classification pipeline initialized with model: {CLASSIFICATION_MODEL}")
except Exception as e:
    logging.exception(f"Failed to initialize Hugging Face pipeline: {e}")
    # Depending on the error, you might need to install additional libraries like 'sentencepiece'
    logging.error("Ensure 'transformers' and its dependencies (like 'torch', possibly 'sentencepiece') are installed.")
    sys.exit(1)

# --- Core Functions ---

def get_transcripts_to_tag(conn):
    """Fetches transcripts that need tagging."""
    # Optionally add LIMIT 1 for testing after database reset
    sql = """
        SELECT id, media_id, text -- Or potentially fetch summary text? Let's start with full transcript text.
        FROM content_creation.transcripts
        WHERE status = %s
        ORDER BY created_at
        LIMIT 1; -- REMOVE LIMIT FOR FULL RUN
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (TRANSCRIPT_STATUS_PENDING,))
            transcripts = cursor.fetchall()
            logging.info(f"Found {len(transcripts)} transcript(s) with status '{TRANSCRIPT_STATUS_PENDING}' to tag.")
            return transcripts
    except Exception as e:
        logging.error(f"Error fetching transcripts to tag: {e}")
        return []

def generate_tags_with_classifier(transcript_text):
    """Generates tags using the zero-shot classification pipeline."""
    if not transcript_text or transcript_text.isspace():
        logging.warning("Input text is empty, cannot generate tags.")
        return []

    tags_found = []
    try:
        logging.debug(f"Running zero-shot classification for text (first 100 chars): {transcript_text[:100]}...")
        # The pipeline expects the sequence(s) and the candidate_labels list
        # Set multi_label=True to allow multiple labels to be assigned
        results = classifier(transcript_text, CANDIDATE_LABELS, multi_label=True)

        # Process results - keep labels above the threshold
        if results and 'labels' in results and 'scores' in results:
            for label, score in zip(results['labels'], results['scores']):
                if score >= SCORE_THRESHOLD:
                    tags_found.append({'type': 'topic', 'value': label, 'score': round(score, 4)}) # Default type 'topic' for now
                    logging.debug(f"Tag accepted: {label} (Score: {score:.4f})")
                else:
                    logging.debug(f"Tag rejected (below threshold {SCORE_THRESHOLD}): {label} (Score: {score:.4f})")
        else:
             logging.warning(f"Classifier did not return expected results format for text: {transcript_text[:100]}...")

        logging.info(f"Generated {len(tags_found)} tags for the transcript.")
        return tags_found

    except Exception as e:
        logging.exception(f"Error during tag classification: {e}")
        return [] # Return empty list on error

def save_tags_and_update_status(conn, transcript_id, media_id, tags, new_status):
    """Saves the tags and updates the transcript status in a transaction."""
    insert_sql = """
        INSERT INTO content_creation.content_tags
            (transcript_id, media_id, tag_type, tag_value, model_used, score)
        VALUES (%s, %s, %s, %s, %s, %s);
    """
    update_sql = """
        UPDATE content_creation.transcripts
        SET status = %s
        WHERE id = %s;
    """
    try:
        with conn.cursor() as cursor:
            # Insert tags if any were found
            if tags:
                tag_data = [
                    (transcript_id, media_id, tag.get('type', 'topic'), tag['value'], CLASSIFICATION_MODEL, tag.get('score'))
                    for tag in tags
                ]
                cursor.executemany(insert_sql, tag_data)
                logging.debug(f"Inserted {len(tags)} tags for transcript_id {transcript_id}.")
            else:
                logging.info(f"No tags met the threshold for transcript_id {transcript_id}. Nothing to insert.")

            # Update the transcript status regardless of whether tags were inserted
            cursor.execute(update_sql, (new_status, transcript_id))
            logging.debug(f"Updated status for transcript_id {transcript_id} to '{new_status}'.")

        conn.commit() # Commit transaction
        logging.info(f"Successfully saved tags (if any) and updated status for transcript_id {transcript_id}.")
        return True
    except Exception as e:
        logging.error(f"Database error saving tags/updating status for transcript_id {transcript_id}: {e}")
        conn.rollback()
        return False

def update_transcript_status(conn, transcript_id, status):
    """Updates only the transcript status (e.g., on failure during processing)."""
    sql = """
        UPDATE content_creation.transcripts
        SET status = %s
        WHERE id = %s;
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (status, transcript_id))
        conn.commit()
        logging.warning(f"Updated status for transcript_id {transcript_id} to '{status}' (likely due to processing failure).")
    except Exception as e:
        logging.error(f"Failed to update transcript status to '{status}' for id {transcript_id}: {e}")
        conn.rollback()


# --- Main Orchestration Function ---

def main():
    """Main function to generate tags."""
    logging.info("Starting tag generation process...")
    conn = get_db_connection()
    if not conn:
        logging.error("Could not establish database connection. Exiting.")
        return

    processed_count = 0
    failed_count = 0
    tags_added_count = 0
    try:
        transcripts_to_process = get_transcripts_to_tag(conn)

        if not transcripts_to_process:
            logging.info("No transcripts found needing tagging.")
            return

        for transcript_id, media_id, transcript_text in transcripts_to_process:
            logging.info(f"Processing transcript_id: {transcript_id}")

            # Generate tags
            tags = generate_tags_with_classifier(transcript_text)

            # Save tags (even if list is empty) and update status
            if save_tags_and_update_status(conn, transcript_id, media_id, tags, TRANSCRIPT_STATUS_SUCCESS):
                processed_count += 1
                tags_added_count += len(tags)
            else:
                # Error during DB operation, already logged and rolled back by save_tags function
                # Status remains 'summarized' or whatever it was before tx failed
                failed_count += 1
                # Optional: attempt to set specific failure status here?
                # update_transcript_status(conn, transcript_id, TRANSCRIPT_STATUS_FAILED) -> This could overwrite previous state if tx failed

    except Exception as e:
        logging.exception(f"An unexpected error occurred during the main loop: {e}")
        if conn: conn.rollback()
    finally:
        close_db_connection(conn)
        logging.info(f"Tag generation process finished. Processed: {processed_count}, DB Failed: {failed_count}, Tags Added: {tags_added_count}.")


# --- Script Execution ---
if __name__ == "__main__":
    main()