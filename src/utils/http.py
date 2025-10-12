"""HTTP client utilities with retry logic for both sync and async operations."""
import asyncio
import time
from typing import Optional

import httpx

from .settings import (
    DEFAULT_USER_AGENT,
    DEFAULT_TIMEOUT,
    HTTP_RETRIES,
    HTTP_BACKOFF_FACTOR,
    HTTP_STATUS_FORCELIST
)


class RetryTransport(httpx.HTTPTransport):
    """Custom HTTP transport with retry logic."""
    
    def __init__(
        self,
        retries: int = HTTP_RETRIES,
        backoff_factor: float = HTTP_BACKOFF_FACTOR,
        status_forcelist: list = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist or HTTP_STATUS_FORCELIST
    
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle request with retry logic."""
        for attempt in range(self.retries + 1):
            try:
                response = super().handle_request(request)
                
                # If status is in forcelist, retry
                if response.status_code in self.status_forcelist and attempt < self.retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                
                return response
                
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < self.retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                raise
        
        return response


class AsyncRetryTransport(httpx.AsyncHTTPTransport):
    """Custom async HTTP transport with retry logic."""
    
    def __init__(
        self,
        retries: int = HTTP_RETRIES,
        backoff_factor: float = HTTP_BACKOFF_FACTOR,
        status_forcelist: list = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist or HTTP_STATUS_FORCELIST
    
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle async request with retry logic."""
        response = None
        for attempt in range(self.retries + 1):
            try:
                response = await super().handle_async_request(request)
                
                # If status is in forcelist, retry
                if response.status_code in self.status_forcelist and attempt < self.retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                
                return response
                
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < self.retries:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise
        
        return response


def create_httpx_client(
    user_agent: Optional[str] = None,
    timeout: Optional[int] = None,
    follow_redirects: bool = True
) -> httpx.Client:
    """Create a synchronous httpx client with retries and proper headers.
    
    Args:
        user_agent: Custom user agent string
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow redirects
        
    Returns:
        Configured httpx.Client instance
    """
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT
    }
    
    transport = RetryTransport()
    
    return httpx.Client(
        headers=headers,
        timeout=timeout or DEFAULT_TIMEOUT,
        transport=transport,
        follow_redirects=follow_redirects
    )


def create_async_httpx_client(
    user_agent: Optional[str] = None,
    timeout: Optional[int] = None,
    follow_redirects: bool = True
) -> httpx.AsyncClient:
    """Create an asynchronous httpx client with retries and proper headers.
    
    Args:
        user_agent: Custom user agent string
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow redirects
        
    Returns:
        Configured httpx.AsyncClient instance
    """
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT
    }
    
    transport = AsyncRetryTransport()
    
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout or DEFAULT_TIMEOUT,
        transport=transport,
        follow_redirects=follow_redirects
    )
