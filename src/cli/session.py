"""
Session state management for interactive CLI
"""

import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse


class SimpleSession:
    """Simple session state for interactive CLI"""
    
    def __init__(self):
        # Discovery state
        self.discovered_sources = []
        
        # Current working source
        self.current_url = None
        self.current_source_name = None
        
        # Link schema state
        self.link_schema = None
        self.extracted_urls = []
        
        # Article schema state  
        self.sample_urls = []
        self.article_schema = None
        self.validation_feedback = []
        
        # Cache for ground truth (to avoid re-extraction)
        self.ground_truth_cache = {}
    
    def reset(self):
        """Reset all session state"""
        self.__init__()
    
    def set_url_directly(self, url: str):
        """Set URL directly without discovery"""
        self.current_url = url
        # Extract domain name for display
        parsed = urlparse(url)
        self.current_source_name = parsed.netloc.replace('www.', '')
        
        # Clear any existing schema/sample state
        self.link_schema = None
        self.extracted_urls = []
        self.sample_urls = []
        self.article_schema = None
        self.validation_feedback = []
    
    def has_current_url(self) -> bool:
        """Check if we have a current URL set"""
        return self.current_url is not None
    
    def has_link_schema(self) -> bool:
        """Check if we have a link schema generated"""
        return self.link_schema is not None
    
    def has_sample_urls(self) -> bool:
        """Check if we have sample URLs selected"""
        return len(self.sample_urls) > 0
    
    def has_article_schema(self) -> bool:
        """Check if we have an article schema generated"""
        return self.article_schema is not None
    
    def get_domain(self) -> str:
        """Get the domain for display purposes"""
        if not self.current_url:
            return ""
        parsed = urlparse(self.current_url)
        return parsed.netloc.replace('www.', '')
    
    def get_state_summary(self) -> str:
        """Get a summary of the current state"""
        if not self.current_url:
            return "No URL set"
        
        parts = [f"URL: {self.current_source_name}"]
        
        if self.link_schema:
            parts.append("✅ Link schema")
        else:
            parts.append("❌ Link schema")
            
        if self.sample_urls:
            parts.append(f"✅ {len(self.sample_urls)} samples")
        else:
            parts.append("❌ Samples")
            
        if self.article_schema:
            parts.append("✅ Article schema")
        else:
            parts.append("❌ Article schema")
            
        return " | ".join(parts)
    
    # New methods for CRUD operations on sample URLs
    def add_sample_url(self, url: str) -> bool:
        """Add a URL to the sample list if not already present"""
        if url not in self.sample_urls:
            self.sample_urls.append(url)
            return True
        return False
    
    def remove_sample_url(self, index: int) -> bool:
        """Remove a URL from the sample list by index (1-based)"""
        if 1 <= index <= len(self.sample_urls):
            removed_url = self.sample_urls.pop(index - 1)
            # Also remove from ground truth cache
            if removed_url in self.ground_truth_cache:
                del self.ground_truth_cache[removed_url]
            return True
        return False
    
    def clear_sample_urls(self):
        """Clear all sample URLs and ground truth cache"""
        self.sample_urls.clear()
        self.ground_truth_cache.clear()
    
    def get_sample_url(self, index: int) -> Optional[str]:
        """Get a sample URL by index (1-based)"""
        if 1 <= index <= len(self.sample_urls):
            return self.sample_urls[index - 1] 