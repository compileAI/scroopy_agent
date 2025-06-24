"""
Configuration module for Scroopy agent
"""

import os
import logging
import dspy
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Find .env file - it should be in the project root, two levels up from this file
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
    print(f"✅ Loaded environment variables from {env_path}")
except ImportError:
    print("⚠️ python-dotenv not installed - trying without .env file loading")
except Exception as e:
    print(f"⚠️ Could not load .env file: {e}")

logger = logging.getLogger(__name__)

def setup_dspy_gemini():
    """Setup DSPy with Google Gemini configuration"""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY environment variable not set")
        raise ValueError("GOOGLE_API_KEY is required for Scroopy to function")
    
    try:
        lm = dspy.LM(
            model="gemini/gemini-2.0-flash", 
            api_key=api_key
        )
        dspy.settings.configure(lm=lm)
        logger.info("✅ DSPy initialized with Google Gemini")
        return lm
    except Exception as e:
        logger.error(f"❌ Failed to initialize DSPy with Gemini: {e}")
        raise

# Initialize DSPy when module is imported
try:
    _dspy_lm = setup_dspy_gemini()
    logger.info("🤖 Scroopy ready with Gemini LLM")
except Exception as e:
    logger.warning(f"⚠️ DSPy initialization failed: {e}")
    _dspy_lm = None

def get_dspy_lm():
    """Get the initialized DSPy language model"""
    return _dspy_lm 
