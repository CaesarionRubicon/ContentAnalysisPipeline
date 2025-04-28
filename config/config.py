import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file located in the project root
# Determine the project root directory (assuming config.py is in a 'config' subfolder)
PROJECT_ROOT = Path(__file__).parent.parent
dotenv_path = PROJECT_ROOT / '.env'
# *** MODIFIED THIS LINE ***
load_dotenv(dotenv_path=dotenv_path, override=True)

# --- Database Configuration ---
DB_NAME = os.getenv("DB_NAME", "content_creation")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")  # Load directly from .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Path Configuration ---
# Use pathlib for robust path handling
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = OUTPUT_DIR / "logs"
CLIPS_DIR = OUTPUT_DIR / "clips"

# Specific raw data paths
RAW_VIDEOS_DIR = RAW_DATA_DIR / "videos"
RAW_AUDIO_DIR = RAW_DATA_DIR / "audio"
RAW_TRANSCRIPTS_DIR = RAW_DATA_DIR / "transcripts"
RAW_METADATA_DIR = RAW_DATA_DIR / "metadata"

# Specific processed data paths
EMBEDDINGS_DIR = PROCESSED_DATA_DIR / "embeddings"
SUMMARIES_DIR = PROCESSED_DATA_DIR / "summaries"

# Ensure log directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Model Configuration ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIMENSION = 384  # Corresponds to all-MiniLM-L6-v2

# --- API Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# --- File Handling ---
SUPPORTED_EXTENSIONS = {
    'video': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'],
    'audio': ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
}

# --- Other Settings ---
# Example: BATCH_SIZE = 32

# Simple check to warn if the password is not set in .env
if DB_PASSWORD is None:
    print("WARNING: DB_PASSWORD not found in .env file. Database connections may fail.")

# Check if OPENAI_API_KEY is loaded - Added for clarity during execution
if OPENAI_API_KEY:
    print(f"OpenAI API Key loaded (starts with: {OPENAI_API_KEY[:7]}...).") # Show first few chars
else:
    print("WARNING: OPENAI_API_KEY not found or empty in environment/config.")


print(f"Configuration loaded. Project Root: {PROJECT_ROOT}")
print(f"Log directory: {LOGS_DIR}")