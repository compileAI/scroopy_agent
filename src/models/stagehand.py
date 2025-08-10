from pydantic import BaseModel, Field, field_validator, HttpUrl
import dateparser
from datetime import date
from typing import Optional, List


class LinkList(BaseModel):
    """Model for extracting links from pages."""
    link: HttpUrl = Field(..., min_length=1)   # enforce full URLs


class Article(BaseModel):
    """Model for extracted article content from Stagehand."""
    title: str
    author: str
    date_published: Optional[date] = None
    content: List[str]

    # lenient natural-language date → ISO date
    @field_validator("date_published", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not v:
            return None
        parsed = dateparser.parse(v)
        if not parsed:
            raise ValueError("unparseable date")
        return parsed.date()