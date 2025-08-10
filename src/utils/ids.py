import hashlib
from typing import Optional


def generate_deterministic_id(prefix: str, *parts: str) -> str:
    """Generate a deterministic ID from prefix and parts."""
    # Clean parts and join
    clean_parts = [str(part).strip() for part in parts if part]
    combined = "-".join(clean_parts)
    
    # Create hash for very long IDs
    if len(combined) > 50:
        hash_suffix = hashlib.md5(combined.encode()).hexdigest()[:8]
        combined = f"{combined[:40]}-{hash_suffix}"
    
    return f"{prefix}-{combined}"


def safe_filename(text: str, max_length: int = 100) -> str:
    """Convert text to safe filename, replacing problematic characters."""
    # Replace problematic characters
    safe = text.replace("/", "-").replace("\\", "-").replace(":", "-")
    safe = "".join(c for c in safe if c.isalnum() or c in ".-_")
    
    # Truncate if too long
    if len(safe) > max_length:
        safe = safe[:max_length-8] + "-" + hashlib.md5(text.encode()).hexdigest()[:7]
    
    return safe