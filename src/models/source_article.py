from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SourceArticle:
    """Canonical model for records written to public.source_articles.

    published should be a YYYY-MM-DD string (submitted date). If None/empty, DB can accept null.
    """

    published: Optional[str]
    title: str
    content: str
    author: str
    source_id: int
    url: str
    id: str

