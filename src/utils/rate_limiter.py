"""
Rate limiting utility for API calls to prevent quota exhaustion
"""

import asyncio
import time
import logging
from typing import Callable, Any, Dict, Optional
from functools import wraps
import random

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Rate limiter with exponential backoff and quota tracking
    """
    
    def __init__(self, 
                 requests_per_minute: int = 15,  # Conservative limit for Gemini free tier
                 max_retries: int = 5,
                 base_delay: float = 2.0,
                 max_delay: float = 60.0,
                 jitter: bool = True):
        self.requests_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        
        # Track request timestamps
        self.request_times = []
        self.last_request_time = 0
        
        # Track consecutive failures for backoff
        self.consecutive_failures = 0
        self.last_failure_time = 0
        
    def _clean_old_requests(self):
        """Remove request timestamps older than 1 minute"""
        current_time = time.time()
        cutoff_time = current_time - 60  # 1 minute ago
        self.request_times = [t for t in self.request_times if t > cutoff_time]
    
    def _calculate_delay(self) -> float:
        """Calculate delay based on rate limits and backoff"""
        current_time = time.time()
        
        # Clean old requests
        self._clean_old_requests()
        
        # Check if we need to wait for rate limit
        if len(self.request_times) >= self.requests_per_minute:
            oldest_request = min(self.request_times)
            rate_limit_delay = 60 - (current_time - oldest_request) + 1  # +1 second buffer
            if rate_limit_delay > 0:
                logger.info(f"⏱️ Rate limit delay: {rate_limit_delay:.1f}s")
                return rate_limit_delay
        
        # Check minimum delay between requests
        min_delay = 60 / self.requests_per_minute  # Spread requests evenly
        time_since_last = current_time - self.last_request_time
        if time_since_last < min_delay:
            basic_delay = min_delay - time_since_last
            logger.info(f"⏱️ Basic rate limiting delay: {basic_delay:.1f}s")
            return basic_delay
        
        # Exponential backoff for consecutive failures
        if self.consecutive_failures > 0:
            backoff_delay = min(
                self.base_delay * (2 ** (self.consecutive_failures - 1)),
                self.max_delay
            )
            
            # Add jitter to prevent thundering herd
            if self.jitter:
                backoff_delay *= (0.5 + random.random() * 0.5)
            
            logger.info(f"⏱️ Exponential backoff delay: {backoff_delay:.1f}s (failures: {self.consecutive_failures})")
            return backoff_delay
        
        return 0
    
    async def wait_if_needed(self):
        """Wait if rate limiting is needed"""
        delay = self._calculate_delay()
        if delay > 0:
            logger.info(f"🛑 Rate limiting: waiting {delay:.1f} seconds...")
            await asyncio.sleep(delay)
    
    def record_request(self):
        """Record a successful request"""
        current_time = time.time()
        self.request_times.append(current_time)
        self.last_request_time = current_time
        self.consecutive_failures = 0  # Reset failure count on success
    
    def record_failure(self, error: Exception):
        """Record a failed request for backoff calculation"""
        current_time = time.time()
        self.consecutive_failures += 1
        self.last_failure_time = current_time
        
        # Check if it's a rate limit error
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ['rate limit', 'quota', 'resource_exhausted', '429']):
            logger.warning(f"🚫 Rate limit error detected: {error}")
            # Increase backoff more aggressively for rate limit errors
            self.consecutive_failures += 2
        else:
            logger.warning(f"⚠️ API error: {error}")

# Global rate limiter instance
_global_rate_limiter = RateLimiter()

def rate_limited(func: Callable) -> Callable:
    """
    Decorator to add rate limiting to async functions
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global _global_rate_limiter
        
        for attempt in range(_global_rate_limiter.max_retries):
            try:
                # Wait if rate limiting is needed
                await _global_rate_limiter.wait_if_needed()
                
                # Make the API call
                result = await func(*args, **kwargs)
                
                # Record successful request
                _global_rate_limiter.record_request()
                
                return result
                
            except Exception as e:
                # Record the failure
                _global_rate_limiter.record_failure(e)
                
                # Check if we should retry
                if attempt < _global_rate_limiter.max_retries - 1:
                    error_str = str(e).lower()
                    
                    # Always retry on rate limit errors
                    if any(keyword in error_str for keyword in ['rate limit', 'quota', 'resource_exhausted', '429']):
                        logger.warning(f"🔄 Rate limit hit, retrying in {_global_rate_limiter._calculate_delay():.1f}s (attempt {attempt + 1}/{_global_rate_limiter.max_retries})")
                        continue
                    
                    # Retry on server errors
                    elif any(keyword in error_str for keyword in ['503', 'server error', 'unavailable', 'timeout']):
                        logger.warning(f"🔄 Server error, retrying (attempt {attempt + 1}/{_global_rate_limiter.max_retries}): {e}")
                        continue
                    
                    # Don't retry on client errors (400, 401, etc.)
                    else:
                        logger.error(f"❌ Non-retryable error: {e}")
                        raise e
                else:
                    logger.error(f"❌ Max retries ({_global_rate_limiter.max_retries}) exceeded: {e}")
                    raise e
        
        # This should never be reached
        raise Exception("Unexpected end of retry loop")
    
    return wrapper

async def wait_for_rate_limit():
    """Manually trigger rate limiting wait"""
    global _global_rate_limiter
    await _global_rate_limiter.wait_if_needed()

def reset_rate_limiter():
    """Reset the rate limiter state"""
    global _global_rate_limiter
    _global_rate_limiter = RateLimiter()
    logger.info("🔄 Rate limiter reset")

def get_rate_limiter_stats() -> Dict[str, Any]:
    """Get current rate limiter statistics"""
    global _global_rate_limiter
    _global_rate_limiter._clean_old_requests()
    
    return {
        "requests_in_last_minute": len(_global_rate_limiter.request_times),
        "requests_per_minute_limit": _global_rate_limiter.requests_per_minute,
        "consecutive_failures": _global_rate_limiter.consecutive_failures,
        "time_since_last_request": time.time() - _global_rate_limiter.last_request_time,
        "next_delay": _global_rate_limiter._calculate_delay()
    } 