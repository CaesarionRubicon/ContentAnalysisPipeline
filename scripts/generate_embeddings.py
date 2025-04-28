import os
import sys
import logging
# Remove argparse for now as it wasn't being used
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values # Efficient batch inserts
from pathlib import Path
from sentence_transformers import SentenceTransformer # Import the library

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config # Import settings from config/config.py
from scripts import db_utils # Import database utilities

# --- Logging Setup ---
# (Consider refactoring logging setup into a shared utility later)
log_file = config.LOGS_DIR / 'embedding_generation.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- REMOVED local get_db_connection function ---

# --- Main Embedding Generation Function ---

def generate_embeddings(batch_size=32):
    """Generates embeddings for transcript segments that don't have them yet."""
    logging.info("Starting embedding generation process...")
    conn = db_utils.get_db_connection() # <<< USE DB UTILS
    if not conn:
        return # Cannot proceed without DB connection

    try:
        # Load the Sentence Transformer model specified in config
        model_name = config.EMBEDDING_MODEL
        logging.info(f"Loading Sentence Transformer model: {model_name}")
        model = SentenceTransformer(model_name, device='cuda')
        logging.info(f"Model '{model_name}' loaded successfully.")

        total_embedded_count = 0
        while True: # Loop to process in batches until no more transcripts are found
            transcripts_to_embed = []
            with conn.cursor() as cur:
                logging.info(f"Fetching batch of {batch_size} transcripts to embed...")
                cur.execute(
                    sql.SQL("""
                        SELECT t.id, t.media_id, t.text
                        FROM content_creation.transcripts t
                        LEFT JOIN content_creation.embeddings e ON t.id = e.transcript_id AND e.model_name = %s
                        WHERE e.transcript_id IS NULL
                        LIMIT %s;
                    """),
                    (model_name, batch_size)
                )
                results = cur.fetchall()

                if not results:
                    logging.info("No more transcripts found needing embedding with this model.")
                    break # Exit the loop if no results

                logging.info(f"Found {len(results)} transcripts in this batch.")
                transcripts_to_embed = results

            transcript_ids = [row[0] for row in transcripts_to_embed]
            media_ids = [row[1] for row in transcripts_to_embed]
            texts = [row[2] for row in transcripts_to_embed]

            logging.info(f"Generating embeddings for {len(texts)} text segments...")
            embeddings = model.encode(texts, show_progress_bar=True, batch_size=batch_size)
            logging.info(f"Generated {len(embeddings)} embeddings.")

            embedding_data_tuples = []
            for i in range(len(transcript_ids)):
                embedding_list = embeddings[i].tolist()
                embedding_data_tuples.append((
                    media_ids[i],
                    transcript_ids[i],
                    f"Transcript segment id {transcript_ids[i]}",
                    model_name,
                    embedding_list
                ))

            if embedding_data_tuples:
                logging.info(f"Inserting {len(embedding_data_tuples)} embeddings into the database...")
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        INSERT INTO content_creation.embeddings
                            (media_id, transcript_id, description, model_name, embedding)
                        VALUES %s;
                        """,
                        embedding_data_tuples,
                        template="(%s, %s, %s, %s, %s::vector)",
                        page_size=100
                    )
                conn.commit()
                total_embedded_count += len(embedding_data_tuples)
                logging.info(f"Successfully inserted batch. Total embedded so far: {total_embedded_count}")
            else:
                 logging.warning("No embedding data tuples generated for this batch.")


    except psycopg2.Error as e:
        logging.error(f"Database error during embedding generation: {e}")
        if conn: conn.rollback()
    except ImportError:
        logging.error("Failed to import SentenceTransformer. Is it installed? (pip install sentence-transformers)")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
    finally:
        # Use db_utils to close the connection
        db_utils.close_db_connection(conn, "generate_embeddings") # <<< USE DB UTILS

    logging.info(f"Embedding generation process finished. Total segments embedded in this run: {total_embedded_count}")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Embedding Generation Script ---")
    generate_embeddings() # Use default batch size for now
    logging.info("--- Embedding Generation Script Finished ---")