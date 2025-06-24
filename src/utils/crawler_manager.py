"""
Centralized Crawler Manager for Scroopy Agent

This module provides a singleton crawler manager that maintains a single browser
instance throughout the agent's lifecycle, preventing browser context conflicts.
"""

import asyncio
import logging
import sys
import signal
import atexit
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Global crawler instance
_shared_crawler = None
_crawler_lock = asyncio.Lock()

async def get_shared_crawler():
    """Get or create the shared crawler instance"""
    global _shared_crawler, _crawler_lock
    
    async with _crawler_lock:
        if _shared_crawler is None:
            logger.info("🕷️ Creating shared browser session")
            
            try:
                # Import here to avoid circular imports
                from crawl4ai import AsyncWebCrawler
                
                # Create new crawler with simple configuration
                # Don't call awarmup() here - let it warm up on first use
                _shared_crawler = AsyncWebCrawler(
                    verbose=True,
                    headless=True
                )
                
                logger.info("✅ Shared browser session created successfully")
                
                # Register cleanup handlers for proper resource management
                _register_cleanup_handlers()
                
            except Exception as e:
                logger.error(f"❌ Failed to create shared crawler: {e}")
                _shared_crawler = None
                raise
        
        return _shared_crawler

def _register_cleanup_handlers():
    """Register cleanup handlers for proper resource management on Windows"""
    try:
        # Register atexit handler for normal program termination
        atexit.register(_sync_cleanup)
        
        # Register signal handlers for graceful shutdown (Unix-like systems)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, _signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, _signal_handler)
            
        logger.info("📋 Cleanup handlers registered")
    except Exception as e:
        logger.warning(f"⚠️ Could not register cleanup handlers: {e}")

def _signal_handler(signum, frame):
    """Handle signals for graceful shutdown"""
    logger.info(f"🔔 Received signal {signum}, initiating cleanup...")
    _sync_cleanup()

def _sync_cleanup():
    """Synchronous cleanup function for atexit/signal handlers"""
    try:
        # Get the current event loop, or create one if none exists
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule cleanup as a task
                loop.create_task(_async_cleanup())
            else:
                # If loop is not running, run cleanup synchronously
                loop.run_until_complete(_async_cleanup())
        except RuntimeError:
            # No event loop exists, create a new one
            asyncio.run(_async_cleanup())
    except Exception as e:
        logger.warning(f"⚠️ Error during sync cleanup: {e}")

async def _async_cleanup():
    """Async cleanup implementation"""
    global _shared_crawler
    
    if _shared_crawler is not None:
        try:
            logger.info("🛑 Cleaning up shared browser session...")
            
            # Try different cleanup methods in order of preference
            cleanup_methods = ['aclose', 'close', '__aexit__']
            cleaned_up = False
            
            for method_name in cleanup_methods:
                if hasattr(_shared_crawler, method_name):
                    try:
                        method = getattr(_shared_crawler, method_name)
                        if callable(method):
                            logger.info(f"   🧪 Trying {method_name}()...")
                            
                            import inspect
                            if inspect.iscoroutinefunction(method):
                                # It's async
                                if method_name == '__aexit__':
                                    await method(None, None, None)
                                else:
                                    await method()
                            else:
                                # It's sync
                                if method_name == '__aexit__':
                                    method(None, None, None)
                                else:
                                    method()
                            
                            logger.info(f"   ✅ Successfully cleaned up with {method_name}()")
                            cleaned_up = True
                            break
                            
                    except Exception as method_error:
                        logger.warning(f"   ⚠️ {method_name}() failed: {method_error}")
                        continue
            
            if not cleaned_up:
                logger.warning("   ⚠️ No cleanup method worked, browser may not be properly closed")
            else:
                logger.info("✅ Browser session cleaned up successfully")
                
            _shared_crawler = None
            
        except Exception as e:
            logger.warning(f"⚠️ Error during async cleanup: {e}")
            _shared_crawler = None  # Set to None anyway to prevent repeated attempts

async def reset_crawler():
    """Reset the shared crawler - useful for tests"""
    global _shared_crawler, _crawler_lock
    
    async with _crawler_lock:
        if _shared_crawler is not None:
            try:
                logger.info("🧹 Resetting shared browser session")
                
                # Try different cleanup methods in order of preference
                cleanup_methods = ['aclose', 'close', '__aexit__']
                cleaned_up = False
                
                for method_name in cleanup_methods:
                    if hasattr(_shared_crawler, method_name):
                        try:
                            method = getattr(_shared_crawler, method_name)
                            if callable(method):
                                import inspect
                                if inspect.iscoroutinefunction(method):
                                    # It's async
                                    if method_name == '__aexit__':
                                        await method(None, None, None)
                                    else:
                                        await method()
                                else:
                                    # It's sync
                                    if method_name == '__aexit__':
                                        method(None, None, None)
                                    else:
                                        method()
                                
                                cleaned_up = True
                                break
                                
                        except Exception as method_error:
                            logger.warning(f"⚠️ Reset {method_name}() failed: {method_error}")
                            continue
                
                if not cleaned_up:
                    logger.warning("⚠️ No reset method worked")
                    
            except Exception as e:
                logger.warning(f"⚠️ Error during crawler reset: {e}")
            finally:
                _shared_crawler = None

async def close_crawler():
    """Close the shared crawler"""
    await _async_cleanup() 