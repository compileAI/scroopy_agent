"""
Logging configuration for Scroopy agent
"""

import logging

def setup_logging():
    """Setup logging configuration for Scroopy"""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Reduce verbose logging from other libraries
    logging.getLogger('LiteLLM').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('crawl4ai').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("✅ Logging configured for Scroopy")
    
    return logger 
