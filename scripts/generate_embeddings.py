import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values # Efficient batch inserts
from pathlib import Path
from sentence_transformers import SentenceTransformer # Import the library

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config # Import settings from config/config.py

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

# --- Database Connection Function ---
# (Consider refactoring DB connection into a shared utility later)
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
        logging.debug(f"DB connection established to {config.DB_NAME}@{config.DB_HOST}")
        return conn
    except psycopg2.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

# --- Main Embedding Generation Function ---

def generate_embeddings(batch_size=32):
    """Generates embeddings for transcript segments that don't have them yet."""
    logging.info("Starting embedding generation process...")
    conn = get_db_connection()
    if not conn:
        return # Cannot proceed without DB connection

    try:
        # Load the Sentence Transformer model specified in config
        model_name = config.EMBEDDING_MODEL
        logging.info(f"Loading Sentence Transformer model: {model_name}")
        # Specify trust_remote_code=True if using certain newer community models
        # Add device='cuda' if torch with CUDA is installed and you want to force GPU
        model = SentenceTransformer(model_name, device='cuda')
        logging.info(f"Model '{model_name}' loaded successfully.")
        # Verify dimension matches config (optional but good practice)
        # assert model.get_sentence_embedding_dimension() == config.EMBEDDING_DIMENSION, \
        #     f"Model dimension mismatch: Model={model.get_sentence_embedding_dimension()}, Config={config.EMBEDDING_DIMENSION}"


        total_embedded_count = 0
        while True: # Loop to process in batches until no more transcripts are found
            transcripts_to_embed = []
            with conn.cursor() as cur:
                # Find transcripts that don't have an entry in the embeddings table yet
                logging.info(f"Fetching batch of {batch_size} transcripts to embed...")
                cur.execute(
                    sql.SQL("""
                        SELECT t.id, t.media_id, t.text
                        FROM content_creation.transcripts t
                        LEFT JOIN content_creation.embeddings e ON t.id = e.transcript_id AND e.model_name = %s
                        WHERE e.transcript_id IS NULL
                        LIMIT %s;
                    """),
                    (model_name, batch_size) # Filter by model_name too!
                )
                results = cur.fetchall()

                if not results:
                    logging.info("No more transcripts found needing embedding with this model.")
                    break # Exit the loop if no results

                logging.info(f"Found {len(results)} transcripts in this batch.")
                transcripts_to_embed = results

            # Prepare data for encoding
            transcript_ids = [row[0] for row in transcripts_to_embed]
            media_ids = [row[1] for row in transcripts_to_embed]
            texts = [row[2] for row in transcripts_to_embed]

            # Generate embeddings for the batch
            logging.info(f"Generating embeddings for {len(texts)} text segments...")
            embeddings = model.encode(texts, show_progress_bar=True, batch_size=batch_size) # Use model's batch size
            logging.info(f"Generated {len(embeddings)} embeddings.")

            # Prepare data for database insertion
            embedding_data_tuples = []
            for i in range(len(transcript_ids)):
                # Ensure embedding is a list of floats for compatibility, although not strictly necessary for pgvector/psycopg2
                embedding_list = embeddings[i].tolist()
                embedding_data_tuples.append((
                    media_ids[i],
                    transcript_ids[i],
                    f"Transcript segment id {transcript_ids[i]}", # Basic description
                    model_name,
                    embedding_list # Pass the vector
                ))

            # Insert embeddings into the database using execute_values for efficiency
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
                        template="(%s, %s, %s, %s, %s::vector)", # Explicitly cast to vector type
                        page_size=100 # Adjust page size based on performance/memory
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
        traceback.print_exc() # Print full traceback for unexpected errors
        if conn: conn.rollback()
    finally:
        if conn and not conn.closed:
            conn.close()
            logging.info("Database connection closed.")

    logging.info(f"Embedding generation process finished. Total segments embedded in this run: {total_embedded_count}")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Embedding Generation Script ---")
    # Add command-line arguments if needed later (e.g., --batch-size, --model-name)
    # parser = argparse.ArgumentParser(description="Generate embeddings for transcripts.")
    # parser.add_argument("--batch_size", type=int, default=32, help="Number of transcripts to process in each batch.")
    # args = parser.parse_args()
    # generate_embeddings(batch_size=args.batch_size)

    generate_embeddings() # Use default batch size for now

    logging.info("--- Embedding Generation Script Finished ---")