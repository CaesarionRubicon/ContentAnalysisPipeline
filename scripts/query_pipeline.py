import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor # Use DictCursor for easier row access
from pathlib import Path
from sentence_transformers import SentenceTransformer
import torch # Import torch for device management

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config
from scripts import db_utils

# --- Logging Setup ---
log_file = config.LOGS_DIR / 'query.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- Load Embedding Model ---
try:
    logging.info(f"Loading Sentence Transformer model for querying: {config.EMBEDDING_MODEL}")
    # Determine device based on torch import
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.info(f"Using device: {device}")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
    logging.info("Query model loaded successfully.")
# Keep a general exception handler
except Exception as e:
    logging.error(f"Failed to load Sentence Transformer model: {e}")
    logging.warning("Falling back to CPU if model loading failed.")
    # Optionally try loading on CPU explicitly if the first attempt failed
    try:
         embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device='cpu')
         logging.info("Query model loaded successfully on CPU (fallback).")
    except Exception as e2:
         logging.error(f"Failed to load Sentence Transformer model on CPU as fallback: {e2}")
         embedding_model = None # Ensure it's None if all fails

# --- Enhanced Semantic Search Function ---
def semantic_search_with_tags(query_text, top_n=5, filter_tag_type=None, filter_tag_value=None):
    """Performs semantic search, optionally filtering by tags."""
    if not embedding_model:
        logging.error("Embedding model not loaded. Cannot perform search.")
        return []
    if not query_text:
        logging.error("Query text cannot be empty.")
        return []

    conn = db_utils.get_db_connection()
    if not conn:
        return []

    initial_results = []
    final_results = []
    try:
        # 1. Initial Semantic Search
        logging.info(f"Generating embedding for query: '{query_text}'")
        query_embedding = embedding_model.encode(query_text)
        query_embedding_list = query_embedding.tolist()

        logging.info(f"Searching database for top {top_n * 5} potential segments...") # Fetch more candidates initially
        with conn.cursor(cursor_factory=DictCursor) as cur: # Use DictCursor
            cur.execute(
                sql.SQL("""
                    SELECT
                        e.id AS embedding_id,
                        e.transcript_id,
                        t.media_id,
                        t.start_sec,
                        t.end_sec,
                        t.text,
                        m.filename,
                        m.source_uri, -- Added source_uri
                        e.embedding <=> %s::vector AS distance
                    FROM content_creation.embeddings e
                    JOIN content_creation.transcripts t ON e.transcript_id = t.id
                    JOIN content_creation.media m ON t.media_id = m.id
                    WHERE e.model_name = %s
                    ORDER BY distance ASC
                    LIMIT %s; -- Fetch more candidates initially if filtering
                """),
                (
                    query_embedding_list,
                    config.EMBEDDING_MODEL,
                    top_n * 5 if (filter_tag_type and filter_tag_value) else top_n # Fetch more if filtering
                )
            )
            initial_results = cur.fetchall() # List of DictRow objects
            logging.info(f"Found {len(initial_results)} initial candidate results.")

            if not initial_results:
                return [] # No semantic matches found

            # Convert DictRow results to regular dictionaries for easier manipulation
            initial_results = [dict(row) for row in initial_results]

            # 2. Filter by Tags (if requested)
            if filter_tag_type and filter_tag_value:
                logging.info(f"Filtering results by tag_type='{filter_tag_type}' and tag_value='{filter_tag_value}'...")
                candidate_transcript_ids = [res['transcript_id'] for res in initial_results]

                # Query the tags table for transcripts that have the desired tag
                cur.execute(
                    sql.SQL("""
                        SELECT DISTINCT transcript_id
                        FROM content_creation.content_tags
                        WHERE transcript_id = ANY(%s) -- Check only within initial candidates
                          AND tag_type = %s
                          AND tag_value ILIKE %s; -- Use ILIKE for case-insensitive matching
                    """),
                    (
                        candidate_transcript_ids,
                        filter_tag_type,
                        f"%{filter_tag_value}%" # Use wildcard matching for flexibility? Or exact match? Let's use wildcard.
                        # Use filter_tag_value directly for exact case-insensitive match: filter_tag_value
                    )
                )
                matching_transcript_ids = {row['transcript_id'] for row in cur.fetchall()} # Set for fast lookup
                logging.info(f"Found {len(matching_transcript_ids)} transcripts matching the tag filter among candidates.")

                # Keep only results whose transcript_id is in the matching set
                filtered_results = [res for res in initial_results if res['transcript_id'] in matching_transcript_ids]

                # Limit to original top_n after filtering
                final_results = filtered_results[:top_n]
                logging.info(f"Returning {len(final_results)} results after tag filtering.")

            else:
                # No tag filtering requested, return top N semantic results directly
                final_results = initial_results[:top_n] # Ensure limit if we fetched more initially
                logging.info(f"No tag filtering applied. Returning top {len(final_results)} semantic results.")

            # 3. (Optional) Fetch Summaries/Tags for final results
            if final_results:
                 final_transcript_ids = [res['transcript_id'] for res in final_results]
                 # Fetch summaries
                 cur.execute(
                     sql.SQL("""
                        SELECT transcript_id, summary_text
                        FROM content_creation.summaries
                        WHERE transcript_id = ANY(%s);
                     """), (final_transcript_ids,)
                 )
                 summaries = {row['transcript_id']: row['summary_text'] for row in cur.fetchall()}

                 # Fetch tags
                 cur.execute(
                     sql.SQL("""
                         SELECT transcript_id, tag_type, tag_value, score
                         FROM content_creation.content_tags
                         WHERE transcript_id = ANY(%s)
                         ORDER BY transcript_id, score DESC;
                      """), (final_transcript_ids,)
                 )
                 tags = {} # Initialize an empty dictionary for tags
                 for row in cur.fetchall():
                     t_id = row['transcript_id']
                     if t_id not in tags:
                         tags[t_id] = [] # Initialize an empty list for this transcript_id
                     # Format and append the current tag to the list for this transcript_id
                     tag_string = f"{row['tag_type']}:{row['tag_value']} ({row['score']:.2f})" # Store formatted string
                     tags[t_id].append(tag_string)

                 # Add summaries and tags to the results dictionaries
                 for res in final_results:
                     res['summary'] = summaries.get(res['transcript_id'], 'N/A')
                     # Get the list of tags for this transcript_id, default to empty list if none found
                     res['tags'] = tags.get(res['transcript_id'], []) # <<< THIS LOOKS CORRECT


    except psycopg2.Error as e:
        logging.error(f"Database error during search: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.exception(f"An unexpected error occurred during search: {e}") # Use logging.exception for traceback
    finally:
        db_utils.close_db_connection(conn) # Ensure connection is closed

    return final_results


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Query Script ---")
    parser = argparse.ArgumentParser(description="Query the database using semantic search, optionally filtering by tags.")
    parser.add_argument("query", type=str, help="The text query for semantic search.")
    parser.add_argument("-n", "--top_n", type=int, default=5, help="Number of top results to retrieve.")
    # *** NEW ARGUMENTS ***
    parser.add_argument("--tag-type", type=str, help="Filter results by tag type (e.g., 'topic', 'action').")
    parser.add_argument("--tag-value", type=str, help="Filter results by tag value (e.g., 'music', 'technology'). Case-insensitive partial match.")

    args = parser.parse_args()

    # *** Validation for tag arguments ***
    if args.tag_value and not args.tag_type:
        parser.error("--tag-type is required when --tag-value is provided.")
    if args.tag_type and not args.tag_value:
         parser.error("--tag-value is required when --tag-type is provided.")

    if embedding_model:
        search_results = semantic_search_with_tags(
            args.query,
            args.top_n,
            args.tag_type,
            args.tag_value
        )

        if search_results:
            print("\n--- Search Results ---")
            for i, res in enumerate(search_results):
                print(f"\nResult {i+1}: Distance={res['distance']:.4f}")
                print(f"  Media: {res['filename']} (ID: {res['media_id']})")
                print(f"  Source: {res['source_uri']}") # Added source_uri display
                print(f"  Time: {res['start_sec']:.2f}s - {res['end_sec']:.2f}s")
                print(f"  Transcript (ID: {res['transcript_id']}): {res['text']}")
                print(f"  Summary: {res.get('summary', 'N/A')}") # Display summary
                print(f"  Tags: {', '.join(res.get('tags', ['N/A']))}") # Display tags
            print("\n--- End of Results ---")
        else:
            print("No results found matching your criteria or an error occurred.")

    logging.info("--- Query Script Finished ---")