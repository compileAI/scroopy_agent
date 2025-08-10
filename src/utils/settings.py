import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

# Stagehand configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# HTTP configuration
DEFAULT_USER_AGENT = os.getenv(
    'HF_SCRAPER_UA',
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

# Timeout and retry configuration
DEFAULT_TIMEOUT = 30
HTTP_RETRIES = 5
HTTP_BACKOFF_FACTOR = 0.5
HTTP_STATUS_FORCELIST = [429, 500, 502, 503, 504]

# HuggingFace Papers configuration
HF_PAPERS_URL = "https://huggingface.co/papers"
HF_PAPERS_SOURCE_ID = 131
