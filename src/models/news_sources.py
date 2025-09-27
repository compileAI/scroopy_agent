"""
News source models - direct port from compile for database compatibility.
These models must remain identical between compile and scroopy_agent.
"""
from dataclasses import dataclass
from datetime import date
from typing import List
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsSource:
    """Base news source model."""
    name: str
    home_url: str
    source_id: int 
    created_at: date  # These will be set by the database

    # DO NOT CHANGE THIS STRUCTURE UNLESS THOSE CHANGES ARE ALSO REFLECTED IN THE DB

    _registry = {}

    # We'll use this method to get (or create if it doesn't exist) an instance of a news source, ensuring
    # that each reference refers to the same instance
    @classmethod
    def get_instance(cls, name: str, rss_url, home_url):
        if name not in cls._registry:
            cls._registry[name] = NewsSource(name, rss_url, home_url)
        return cls._registry[name]


@dataclass(frozen=True)
class RssSource(NewsSource):
    """RSS feed source."""
    rss_url: str


@dataclass(frozen=True)
class CrawlSource(NewsSource):
    """Web crawling source with extraction schemas."""
    link_schema: dict
    article_schema: dict


@dataclass(frozen=True)
class RedditSource(NewsSource):
    """Reddit source with subreddit and flair filtering."""
    subreddit: str
    flairs: List[str] = None
