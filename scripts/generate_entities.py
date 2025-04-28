import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from pathlib import Path
import spacy # Import spaCy

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config
from scripts import db_utils # Use the db_utils module

# --- Logging Setup ---
log_file = config.LOGS_DIR / 'entity_generation.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- Load spaCy Model ---
SPACY_MODEL_NAME = "en_core_web_sm"
nlp = None # Initialize nlp to None
try:
    logging.info(f"Loading spaCy model: {SPACY_MODEL_NAME}")
    nlp = spacy.load(SPACY_MODEL_NAME, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])
    logging.info(f"spaCy model '{SPACY_MODEL_NAME}' loaded successfully.")
except OSError:
    logging.error(f"spaCy model '{SPACY_MODEL_NAME}' not found. Please download it: python -m spacy download {SPACY_MODEL_NAME}")
except Exception as e:
    logging.error(f"Error loading spaCy model '{SPACY_MODEL_NAME}': {e}")


# --- Main Entity Generation Function ---
def generate_entities(batch_size=50):
    """Processes transcripts with spaCy to find and store named entities."""
    if not nlp:
        logging.error("spaCy model not loaded. Cannot generate entities.")
        return

    logging.info("Starting entity generation process...")
    conn = db_utils.get_db_connection()
    if not conn:
        return

    total_entity_count = 0
    processed_transcript_count = 0

    try:
        while True: # Loop to process in batches
            target_transcripts = []
            processed_ids_in_batch = [] # Keep track of IDs processed in this specific batch
            with conn.cursor() as cur:
                # Find transcripts that are pending enrichment
                logging.info(f"Fetching batch of {batch_size} transcripts needing entity extraction (status='pending_enrichment')...")
                cur.execute(
                    sql.SQL("""
                        SELECT t.id, t.media_id, t.text
                        FROM content_creation.transcripts t
                        WHERE t.status = 'pending_enrichment' -- <<< SELECT BASED ON STATUS
                        LIMIT %s;
                    """),
                    (batch_size,)
                )
                results = cur.fetchall()

                if not results:
                    logging.info("No more transcripts found needing entity extraction.")
                    break # Exit the loop if no results

                logging.info(f"Found {len(results)} transcripts in this batch.")
                target_transcripts = results
                # Store IDs immediately for status update later
                processed_ids_in_batch = [row[0] for row in target_transcripts]
                processed_transcript_count += len(results)


            # Prepare texts for spaCy processing
            # Use tuple format: (text, context_dict)
            texts_with_context = [(row[2], {"transcript_id": row[0], "media_id": row[1]}) for row in target_transcripts]

            # Process texts with spaCy using nlp.pipe for efficiency
            logging.info(f"Processing {len(texts_with_context)} transcripts with spaCy...")
            entity_data_tuples = []
            # Adjust n_process based on CPU cores, batch_size based on memory
            # Make sure nlp.pipe gets the texts correctly from texts_with_context
            for doc, context in nlp.pipe(texts_with_context, as_tuples=True, batch_size=10, n_process=1):
                transcript_id = context["transcript_id"]
                media_id = context["media_id"]
                doc_entity_count = 0
                for ent in doc.ents:
                    entity_data_tuples.append((
                        transcript_id,
                        media_id,
                        ent.text,       # The detected entity text
                        ent.label_,     # The entity label (e.g., PERSON, ORG)
                        ent.start_char, # Start character offset
                        ent.end_char    # End character offset
                    ))
                    doc_entity_count += 1
                # No need for debug log per doc unless troubleshooting
                # if doc_entity_count > 0:
                #      logging.debug(f"Found {doc_entity_count} entities in transcript ID {transcript_id}")

            # --- UPDATE STATUS for processed transcripts --- <<< ADDED THIS BLOCK
            if processed_ids_in_batch:
                logging.info(f"Updating status to 'entities_extracted' for {len(processed_ids_in_batch)} processed transcripts...")
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            sql.SQL("""
                                UPDATE content_creation.transcripts
                                SET status = 'entities_extracted'
                                WHERE id = ANY(%s); -- Use ANY for efficient update on list
                            """),
                            (processed_ids_in_batch,) # Pass the list of IDs processed
                        )
                    conn.commit() # Commit status update
                    logging.info("Status update committed.")
                except psycopg2.Error as e_update:
                     logging.error(f"Database error updating transcript statuses: {e_update}")
                     # Should we rollback the whole batch? Maybe just log error and continue?
                     # For now, log and continue. The next run might retry them if status wasn't updated.
                     if conn: conn.rollback() # Rollback this specific transaction attempt

            # --- Insert entities (if any were found) ---
            if entity_data_tuples:
                logging.info(f"Inserting {len(entity_data_tuples)} entities into the database...")
                try:
                    with conn.cursor() as cur:
                        execute_values(
                            cur,
                            """
                            INSERT INTO content_creation.entities
                                (transcript_id, media_id, text, label, start_char, end_char)
                            VALUES %s;
                            """,
                            entity_data_tuples,
                            template="(%s, %s, %s, %s, %s, %s)",
                            page_size=100
                        )
                    conn.commit() # Commit entity inserts
                    total_entity_count += len(entity_data_tuples)
                    logging.info(f"Successfully inserted batch of entities. Total entities found so far: {total_entity_count}")
                except psycopg2.Error as e_insert:
                     logging.error(f"Database error inserting entities: {e_insert}")
                     if conn: conn.rollback() # Rollback this specific transaction attempt
            else:
                 logging.info("No entities found in this batch of transcripts.")


    except psycopg2.Error as e:
        logging.error(f"Database error during entity generation main loop: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.error(f"An unexpected error occurred during entity generation: {e}")
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
    finally:
        db_utils.close_db_connection(conn, "generate_entities")

    logging.info(f"Entity generation process finished. Processed {processed_transcript_count} transcripts. Found {total_entity_count} entities in this run.")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Entity Generation Script ---")
    if nlp: # Only run if model loaded successfully
        generate_entities()
    else:
        logging.error("Entity generation cannot proceed because spaCy model failed to load.")

    logging.info("--- Entity Generation Script Finished ---")