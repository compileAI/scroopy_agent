import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .settings import DEFAULT_USER_AGENT, DEFAULT_TIMEOUT, HTTP_RETRIES, HTTP_BACKOFF_FACTOR, HTTP_STATUS_FORCELIST


def create_session(user_agent: str = None, timeout: int = None) -> requests.Session:
    """Create a requests session with retries and proper headers."""
    session = requests.Session()
    
    # Configure retries
    retry = Retry(
        total=HTTP_RETRIES,
        backoff_factor=HTTP_BACKOFF_FACTOR,
        status_forcelist=HTTP_STATUS_FORCELIST
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set headers
    session.headers.update({
        "User-Agent": user_agent or DEFAULT_USER_AGENT
    })
    
    # Set default timeout
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    session.timeout = timeout
    
    return session
