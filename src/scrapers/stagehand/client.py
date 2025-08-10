import os
import sys
from typing import Optional

from stagehand import Stagehand, StagehandConfig

# Import settings
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.settings import GEMINI_API_KEY


def create_stagehand_client() -> Stagehand:
    """Create and initialize a Stagehand client."""
    if not GEMINI_API_KEY:
        raise ValueError("❌ GEMINI_API_KEY is required in environment")
    
    config = StagehandConfig(
        env="LOCAL",
        model_name="gemini/gemini-2.0-flash"
    )
    
    return Stagehand(config)


async def get_initialized_client() -> Stagehand:
    """Get an initialized Stagehand client ready for use."""
    client = create_stagehand_client()
    await client.init()
    return client