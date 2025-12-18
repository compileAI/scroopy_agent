import sys
from stagehand import Stagehand

# Import settings
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.stagehand_client_manager import get_stagehand_client, get_stagehand_manager


async def get_initialized_client() -> Stagehand:
    """
    Get an initialized Stagehand client ready for use.
    
    This client comes from a managed pool with automatic key rotation.
    Note: Do NOT call client.close() - the manager handles cleanup.
    """
    return await get_stagehand_client()


def get_manager():
    """Get the Stagehand client manager for advanced operations."""
    return get_stagehand_manager()