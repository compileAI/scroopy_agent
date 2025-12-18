"""
Stagehand Client Pool Manager

Manages a pool of Stagehand clients with automatic rotation on rate limits.
Each client is bound to a different API key for load distribution.
"""

import os
import time
import logging
import asyncio
from typing import List, Optional, Set
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from stagehand import Stagehand, StagehandConfig

load_dotenv()

logger = logging.getLogger(__name__)


class DailyQuotaExhausted(Exception):
    """Raised when the daily API quota is exhausted for all keys."""
    pass


class StagehandClientManager:
    """
    Manages a pool of Stagehand clients with automatic rotation on rate limits.
    
    Features:
    - Pre-initialized pool of clients (one per API key)
    - Automatic rotation on rate limit errors
    - Cooldown period when all clients are rate limited
    - Centralized error handling and logging
    """
    
    def __init__(self, model_name: str = "gemini/gemini-2.5-flash-lite", env: str = "LOCAL"):
        self.api_keys = self._load_api_keys()
        self.model_name = model_name
        self.env = env
        
        # Client pool - indexed by key index
        self.clients: List[Optional[Stagehand]] = [None] * len(self.api_keys)
        self.clients_initialized: List[bool] = [False] * len(self.api_keys)
        
        # Rotation state
        self.current_key_index = 0
        self.rate_limited_keys: Set[int] = set()
        self.last_rotation_time = 0
        self.cooldown_period = 70  # seconds (60s rate limit window + 10s buffer)
        self.cooldown_cycles = 0
        self.max_cooldown_cycles = 10
        
        # Locks for thread safety
        self._rotation_lock = asyncio.Lock()
        self._initialization_locks = [asyncio.Lock() for _ in self.api_keys]
        
        if not self.api_keys:
            raise ValueError("No Gemini API keys found. Please set GOOGLE_API_KEY_1 through GOOGLE_API_KEY_5")
        
        logger.info(f"🔑 Initialized Stagehand Client Manager with {len(self.api_keys)} keys")
    
    def _load_api_keys(self) -> List[str]:
        """Load API keys from environment variables."""
        keys = []
        for i in range(1, 6):  # GOOGLE_API_KEY_1 through GOOGLE_API_KEY_5
            key = os.getenv(f"GOOGLE_API_KEY_{i}")
            if key:
                keys.append(key)
            else:
                logger.debug(f"⚠️ GOOGLE_API_KEY_{i} not found in environment")
        
        # Fallback to original GOOGLE_API_KEY if no numbered keys found
        if not keys:
            original_key = os.getenv("GOOGLE_API_KEY")
            if original_key:
                key_preview = f"{original_key[:4]}...{original_key[-4:]}" if len(original_key) > 8 else "***"
                logger.warning(f"⚠️ Using single GOOGLE_API_KEY: {key_preview} (length: {len(original_key)})")
                logger.warning("⚠️ For rotation, set GOOGLE_API_KEY_1 through GOOGLE_API_KEY_5")
                keys.append(original_key)
            else:
                logger.error("❌ No GOOGLE_API_KEY or GOOGLE_API_KEY_1-5 found in environment!")
        
        logger.info(f"📊 Total API keys loaded: {len(keys)}")
        return keys
    
    async def _initialize_client(self, key_index: int) -> Stagehand:
        """Initialize a Stagehand client for a specific key."""
        async with self._initialization_locks[key_index]:
            # Check if already initialized
            if self.clients_initialized[key_index] and self.clients[key_index] is not None:
                return self.clients[key_index]
            
            # Close existing client if any
            if self.clients[key_index] is not None:
                try:
                    await self.clients[key_index].close()
                except Exception as e:
                    logger.warning(f"⚠️ Error closing old client #{key_index + 1}: {e}")
            
            # Create new client with this key's API key
            api_key = self.api_keys[key_index]

            # Set the API key in environment for Stagehand/litellm to use
            # IMPORTANT: We set both GOOGLE_API_KEY and GEMINI_API_KEY because litellm
            # may look for either depending on the model configuration
            os.environ["GOOGLE_API_KEY"] = api_key
            os.environ["GEMINI_API_KEY"] = api_key
            
            # DEBUG: Verify environment variable was set
            env_key = os.environ.get("GOOGLE_API_KEY")
            if env_key:
                env_preview = f"{env_key[:4]}...{env_key[-4:]}" if len(env_key) > 8 else "***"
                logger.info(f"✅ Environment GOOGLE_API_KEY set: {env_preview} (length: {len(env_key)})")
            else:
                logger.error(f"❌ Failed to set GOOGLE_API_KEY in environment!")
            
            logger.info(f"🔧 Creating StagehandConfig with model: {self.model_name}, env: {self.env}")
            config = StagehandConfig(
                env=self.env,
                model_name=self.model_name
            )
            
            logger.info(f"🚀 Initializing Stagehand client #{key_index + 1}...")
            client = Stagehand(config)
            await client.init()
            
            self.clients[key_index] = client
            self.clients_initialized[key_index] = True
            
            logger.info(f"✅ Successfully initialized Stagehand client #{key_index + 1}")
            logger.info(f"⚠️  API key remains in environment for client #{key_index + 1} to use during operations")
            return client
    
    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if the error indicates a rate limit."""
        error_str = str(error).lower()
        rate_limit_indicators = [
            "rate limit",
            "quota exceeded",
            "too many requests",
            "429",
            "resource exhausted",
            "requests per minute",
            "rpm"
        ]
        
        # Check for HTTP 429 status code
        if hasattr(error, 'status_code') and error.status_code == 429:
            return True
        
        # Check error message for rate limit indicators
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    def _extract_retry_delay(self, error: Exception) -> Optional[float]:
        """
        Extract retry delay from error message if available.
        Returns delay in seconds, or None if not found.
        """
        import re
        error_str = str(error)
        
        try:
            # Try to find "Please retry in X.XXs" pattern
            match = re.search(r'retry in (\d+\.?\d*)s', error_str)
            if match:
                delay = float(match.group(1))
                logger.info(f"📊 API suggests retry delay: {delay:.1f}s")
                return delay
            
            # Try to find retryDelay in JSON
            if 'retryDelay' in error_str:
                match = re.search(r"'retryDelay':\s*'(\d+)s'", error_str)
                if match:
                    delay = float(match.group(1))
                    logger.info(f"📊 API suggests retry delay: {delay:.1f}s")
                    return delay
        except Exception as parse_error:
            logger.warning(f"⚠️ Failed to parse retry delay: {parse_error}")
        
        return None
    
    def _is_daily_quota_error(self, error: Exception) -> bool:
        """
        Check if the error indicates a daily quota exhaustion.
        Looks for 'PerDay' patterns in quotaId field.
        """
        error_str = str(error)
        
        # Look for daily quota indicators
        daily_indicators = [
            'PerDay',
            'PerDayPerUser',
            'PerProjectPerDay',
            'RequestsPerDay'
        ]
        
        # Check if any daily indicator is in the error message
        if any(indicator in error_str for indicator in daily_indicators):
            logger.error(f"🚫 Daily quota exhausted detected in error")
            return True
        
        return False
    
    async def _rotate_to_next_key(self) -> bool:
        """
        Rotate to the next available API key.
        
        Returns:
            bool: True if rotation successful, False if all keys are rate limited
        """
        if len(self.api_keys) == 1:
            logger.warning("⚠️ Only one API key available - cannot rotate")
            return False
        
        # Mark current key as rate limited
        self.rate_limited_keys.add(self.current_key_index)
        logger.warning(f"🚫 Key #{self.current_key_index + 1} hit rate limit")
        
        # Try to find a non-rate-limited key
        attempts = 0
        
        while attempts < len(self.api_keys):
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
            
            if self.current_key_index not in self.rate_limited_keys:
                self.last_rotation_time = time.time()
                logger.info(f"🔄 Rotated to key #{self.current_key_index + 1}")
                return True
        
        # All keys are rate limited
        logger.warning(f"⚠️ All {len(self.api_keys)} API keys are rate limited")
        return False
    
    async def _wait_for_cooldown(self, suggested_delay: Optional[float] = None):
        """Wait for cooldown period and reset rate limited keys."""
        # Increment cooldown cycle counter
        self.cooldown_cycles += 1
        
        # Check if we've exceeded max cooldown cycles
        if self.cooldown_cycles > self.max_cooldown_cycles:
            logger.error(f"❌ Exceeded maximum cooldown cycles ({self.max_cooldown_cycles}). Giving up.")
            raise DailyQuotaExhausted(
                f"Exceeded {self.max_cooldown_cycles} cooldown cycles. "
                "This likely indicates a daily quota exhaustion. "
                "Please check your API quotas or add more API keys."
            )
        
        # Always use suggested delay if available, with +10s buffer
        if suggested_delay:
            wait_time = suggested_delay + 10  # Add 10s buffer to suggested delay
            logger.info(f"⏳ All keys rate limited. Using API suggested delay + buffer: {wait_time:.1f}s")
        else:
            wait_time = self.cooldown_period  # Fall back to 70s
            logger.info(f"⏳ All keys rate limited. Waiting default cooldown: {wait_time:.1f}s")
        
        logger.info(f"📊 Cooldown cycle {self.cooldown_cycles}/{self.max_cooldown_cycles}")
        await asyncio.sleep(wait_time)
        
        # Reset rate limited keys and try the first key again
        self.rate_limited_keys.clear()
        self.current_key_index = 0
        logger.info("🔄 Cooldown complete. Reset to key #1")
    
    async def get_client(self) -> Stagehand:
        """
        Get an available Stagehand client with automatic rate limit handling.
        
        Returns:
            Stagehand: An initialized client ready for use
            
        Raises:
            DailyQuotaExhausted: If daily quota is exhausted
        """
        async with self._rotation_lock:
            max_attempts = len(self.api_keys) * 4  # Allow multiple cooldown cycles
            suggested_delay = None
            
            for attempt in range(max_attempts):
                try:
                    # Get or initialize client for current key
                    client = await self._initialize_client(self.current_key_index)
                    
                    # Ensure the environment variable matches the current client's key
                    # This is important because litellm may read from environment at call time
                    current_api_key = self.api_keys[self.current_key_index]
                    os.environ["GOOGLE_API_KEY"] = current_api_key
                    os.environ["GEMINI_API_KEY"] = current_api_key
                    
                    # Reset cooldown cycles on successful client retrieval
                    self.cooldown_cycles = 0
                    
                    return client
                    
                except Exception as e:
                    if self._is_rate_limit_error(e):
                        logger.warning(f"🚫 Rate limit hit during client initialization (attempt {attempt + 1})")
                        
                        # Check if this is a daily quota error
                        if self._is_daily_quota_error(e):
                            logger.error("❌ Daily quota exhausted for all API keys")
                            raise DailyQuotaExhausted(
                                "Daily API quota exhausted. Please wait for quota reset or add more API keys. "
                                f"Error: {str(e)[:200]}"
                            )
                        
                        # Extract suggested retry delay
                        delay = self._extract_retry_delay(e)
                        if delay:
                            suggested_delay = delay
                        
                        # Try to rotate to next key
                        if await self._rotate_to_next_key():
                            continue  # Try again with new key
                        else:
                            # All keys rate limited - wait for cooldown
                            try:
                                await self._wait_for_cooldown(suggested_delay)
                                suggested_delay = None  # Reset for next cycle
                                continue
                            except DailyQuotaExhausted:
                                raise
                    else:
                        # Non-rate-limit error - propagate
                        logger.error(f"❌ Non-rate-limit error initializing client: {e}")
                        raise
            
            # If we get here, we've exhausted all attempts
            raise Exception(f"Failed to get client after {max_attempts} attempts")
    
    @asynccontextmanager
    async def get_client_context(self):
        """
        Get a client as an async context manager.
        Note: The client is NOT closed after use (it stays in the pool).
        This is just for convenience and error tracking.
        """
        client = await self.get_client()
        try:
            yield client
        except Exception as e:
            # Track rate limit errors
            if self._is_rate_limit_error(e):
                async with self._rotation_lock:
                    self.rate_limited_keys.add(self.current_key_index)
                    logger.warning(f"🚫 Rate limit detected during operation with key #{self.current_key_index + 1}")
            raise
    
    async def report_rate_limit(self, error: Exception):
        """
        Manually report a rate limit error to trigger key rotation.
        Use this when catching rate limit errors in your code.
        """
        if self._is_rate_limit_error(error):
            async with self._rotation_lock:
                self.rate_limited_keys.add(self.current_key_index)
                logger.warning(f"🚫 Rate limit reported for key #{self.current_key_index + 1}")
                
                # Check for daily quota
                if self._is_daily_quota_error(error):
                    raise DailyQuotaExhausted(f"Daily quota exhausted: {str(error)[:200]}")
    
    async def close_all(self):
        """Close all clients in the pool."""
        logger.info("🔒 Closing all Stagehand clients...")
        
        for i, client in enumerate(self.clients):
            if client is not None and self.clients_initialized[i]:
                try:
                    await client.close()
                    logger.info(f"✅ Closed client #{i + 1}")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing client #{i + 1}: {e}")
        
        self.clients = [None] * len(self.api_keys)
        self.clients_initialized = [False] * len(self.api_keys)
        logger.info("🔒 All clients closed")
    
    def get_status(self) -> dict:
        """Get current status of the client manager."""
        return {
            "total_keys": len(self.api_keys),
            "current_key_index": self.current_key_index,
            "rate_limited_keys": list(self.rate_limited_keys),
            "available_keys": [i for i in range(len(self.api_keys)) if i not in self.rate_limited_keys],
            "initialized_clients": sum(self.clients_initialized),
            "cooldown_cycles": self.cooldown_cycles
        }


# Global instance
_stagehand_manager: Optional[StagehandClientManager] = None


def get_stagehand_manager() -> StagehandClientManager:
    """Get the global Stagehand client manager instance."""
    global _stagehand_manager
    if _stagehand_manager is None:
        _stagehand_manager = StagehandClientManager()
    return _stagehand_manager


async def get_stagehand_client() -> Stagehand:
    """Get an available Stagehand client from the pool."""
    manager = get_stagehand_manager()
    return await manager.get_client()
