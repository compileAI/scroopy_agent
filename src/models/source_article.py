from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import logging
from utils.date_utils import safe_parse_date

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logging.warning("BeautifulSoup not available - HTML cleaning will be skipped")

logger = logging.getLogger(__name__)


@dataclass
class SourceArticle:
    """Canonical model for records written to public.source_articles.
    
    Enhanced with functionality from compile's Article model:
    - Auto-generates consistent ID hash
    - Cleans HTML content automatically
    - Handles datetime objects properly
    """

    published: Optional[datetime]  # Changed from str to datetime for consistency
    title: str
    content: str
    author: str
    source_id: int
    url: str
    id: str = field(init=False)  # Auto-generated like compile's Article
    
    def __post_init__(self):
        """Generate ID and clean content automatically."""
        try:
            # Generate ID using same logic as compile for consistency
            key = f"{self.title.strip().lower()}_{self.source_id}"
            self.id = hashlib.sha256(key.encode()).hexdigest()
            self.clean_content()
            logger.debug(f"Created SourceArticle with ID: {self.id[:12]}...")
        except Exception as e:
            logger.error(f"Error in SourceArticle.__post_init__: {e}")
            # Fallback ID generation
            self.id = f"error_{hash(self.title)}_{self.source_id}"
    
    def clean_content(self):
        """Clean HTML content - ported from compile's Article.clean_content()."""
        if not self.content:
            return
            
        try:
            if BeautifulSoup is not None:
                # Remove HTML tags and decode HTML entities
                soup = BeautifulSoup(self.content, 'html.parser')
                content_cleaned = soup.get_text()
                
                # Remove extra whitespace
                content_cleaned = ' '.join(content_cleaned.split())
                
                # Remove newlines
                content_cleaned = content_cleaned.replace('\n', ' ')
                self.content = content_cleaned
                logger.debug("HTML content cleaned successfully")
            else:
                # Fallback: basic HTML tag removal if BeautifulSoup not available
                import re
                self.content = re.sub(r'<[^>]+>', '', self.content)
                self.content = ' '.join(self.content.split())
                logger.warning("Used basic HTML cleaning - install BeautifulSoup for better results")
        except Exception as e:
            logger.error(f"Error cleaning content: {e}")
            # Keep original content if cleaning fails
    
    def to_db_dict(self) -> dict:
        """Convert to database format for consistency."""
        return {
            'id': self.id,
            'published': self.published.isoformat() if self.published else None,
            'title': self.title,
            'content': self.content,
            'author': self.author,
            'source_id': self.source_id,
            'url': self.url
        }
    
    @classmethod
    def from_db_dict(cls, data: dict) -> 'SourceArticle':
        """Create SourceArticle from database data."""
        try:
            # Parse published date if present
            published = None
            if data.get('published'):
                if isinstance(data['published'], str):
                    published = safe_parse_date(data['published'])
                elif isinstance(data['published'], datetime):
                    published = data['published']
            
            article = cls(
                published=published,
                title=data.get('title', ''),
                content=data.get('content', ''),
                author=data.get('author', ''),
                source_id=data.get('source_id', 0),
                url=data.get('url', '')
            )
            
            # Override auto-generated ID with database ID if present
            if data.get('id'):
                article.id = data['id']
                
            return article
        except Exception as e:
            logger.error(f"Error creating SourceArticle from database data: {e}")
            raise

