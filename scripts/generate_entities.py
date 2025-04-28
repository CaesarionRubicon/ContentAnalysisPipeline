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
# Consider making the model name configurable in config.py later
SPACY_MODEL_NAME = "en_core_web_sm"
try:
    logging.info(f"Loading spaCy model: {SPACY_MODEL_NAME}")
    # Disable unnecessary components for NER only pipeline for speed
    nlp = spacy.load(SPACY_MODEL_NAME, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])
    # If only NER is needed and model supports it directly:
    # nlp = spacy.load(SPACY_MODEL_NAME, disable=["parser", "lemmatizer"]) # Keep tagger if needed by NER component
    # Alternatively, just load the NER component if possible in future spaCy versions or custom pipelines
    logging.info(f"spaCy model '{SPACY_MODEL_NAME}' loaded successfully.")
except OSError:
    logging.error(f"spaCy model '{SPACY_MODEL_NAME}' not found. Please download it: python -m spacy download {SPACY_MODEL_NAME}")
    nlp = None
except Exception as e:
    logging.error(f"Error loading spaCy model '{SPACY_MODEL_NAME}': {e}")
    nlp = None


# --- Main Entity Generation Function ---
def generate_entities(batch_size=50): # Process more transcripts at once
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
            with conn.cursor() as cur:
                # Find transcripts that haven't had entities extracted yet
                # We'll track this by seeing if any entity exists for a given transcript_id
                logging.info(f"Fetching batch of {batch_size} transcripts needing entity extraction...")
                cur.execute(
                    sql.SQL("""
                        SELECT t.id, t.media_id, t.text
                        FROM content_creation.transcripts t
                        WHERE NOT EXISTS (
                            SELECT 1 FROM content_creation.entities e
                            WHERE e.transcript_id = t.id
                        )
                        LIMIT %s;
                    """),
                    (batch_size,)
                )
                results = cur.fetchall()

                if not results:
                    logging.info("No more transcripts found needing entity extraction.")
                    break

                logging.info(f"Found {len(results)} transcripts in this batch.")
                target_transcripts = results
                processed_transcript_count += len(results)

            # Prepare texts for spaCy processing
            texts = [(row[2], {"transcript_id": row[0], "media_id": row[1]}) for row in target_transcripts] # Keep metadata

            # Process texts with spaCy using nlp.pipe for efficiency
            logging.info(f"Processing {len(texts)} transcripts with spaCy...")
            entity_data_tuples = []
            # Adjust n_process based on CPU cores, batch_size based on memory
            for doc, context in nlp.pipe(texts, as_tuples=True, batch_size=10, n_process=1):
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
                if doc_entity_count > 0:
                     logging.debug(f"Found {doc_entity_count} entities in transcript ID {transcript_id}")


            # Insert entities into the database using execute_values
            if entity_data_tuples:
                logging.info(f"Inserting {len(entity_data_tuples)} entities into the database...")
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
                conn.commit()
                total_entity_count += len(entity_data_tuples)
                logging.info(f"Successfully inserted batch. Total entities found so far: {total_entity_count}")
            else:
                 logging.info("No entities found in this batch of transcripts.")


    except psycopg2.Error as e:
        logging.error(f"Database error during entity generation: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.error(f"An unexpected error occurred during entity generation: {e}")
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
    finally:
        db_utils.close_db_connection(conn, "generate_entities")

    logging.info(f"Entity generation process finished. Processed {processed_transcript_count} transcripts. Found {total_entity_count} entities.")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Entity Generation Script ---")
    # Add args later if needed (e.g., batch_size)
    # parser = argparse.ArgumentParser(description="Generate named entities from transcripts.")
    # parser.add_argument("--batch_size", type=int, default=50, help="Number of transcripts to process in each batch.")
    # args = parser.parse_args()
    # generate_entities(batch_size=args.batch_size)

    if nlp: # Only run if model loaded successfully
        generate_entities()
    else:
        logging.error("Entity generation cannot proceed because spaCy model failed to load.")

    logging.info("--- Entity Generation Script Finished ---")