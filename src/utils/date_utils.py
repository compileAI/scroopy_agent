"""
Date parsing utilities for the compile AI news pipeline.
Provides safe, robust date parsing with comprehensive error handling.
"""
from datetime import datetime, timezone
from dateutil import parser


def safe_parse_date(date_str: str) -> datetime | None:
    """
    Safely parses a date string into a timezone-aware datetime object using dateutil.parser.
    Handles various date formats including:
    - ISO 8601 (2024-03-14T15:30:00Z)
    - RFC 2822 (Thu, 14 Mar 2024 15:30:00 GMT)
    - Common formats (March 14, 2024, 14 Mar 2024, etc.)
    - Relative dates (yesterday, last week, etc.)
    
    Args:
        date_str (str): The date string to parse
        
    Returns:
        datetime | None: Timezone-aware datetime object if successful, None if parsing fails
    """
    if not date_str or not isinstance(date_str, str) or date_str.strip() == "":
        return None

    # Common date string cleanups
    date_str = date_str.strip()
    
    # Remove timezone abbreviations that might confuse the parser
    date_str = date_str.replace("EST", "").replace("EDT", "").replace("PST", "").replace("PDT", "")
    
    try:
        # Try parsing with fuzzy=True to handle more formats
        parsed_date = parser.parse(date_str, fuzzy=True)
        
        # If the date is naive (no timezone info), assume UTC
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        
        # If the year is in the future, it might be a mistake (e.g., 2025 instead of 2024)
        current_time = datetime.now(timezone.utc)
        if parsed_date.year > current_time.year + 1:
            print(f"⚠️ Warning: Parsed date {parsed_date} is in the future, might be incorrect")
            return None
            
        return parsed_date
        
    except parser.ParserError as e:
        print(f"❌ Failed to parse date: {date_str} ({str(e)})")
        return None
    except Exception as e:
        print(f"❌ Unexpected error parsing date: {date_str} ({str(e)})")
        return None


