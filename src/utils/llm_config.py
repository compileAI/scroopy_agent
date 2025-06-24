"""
LLM Configuration utilities for Scroopy Agent tools
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """LLM configuration data class"""
    provider: str
    api_token: str
    max_tokens: int = 4000
    temperature: float = 0.1

def get_llm_config() -> Optional[LLMConfig]:
    """
    Get LLM configuration from environment variables.
    
    Returns:
        LLMConfig object if configuration is available, None otherwise
    """
    try:
        # Check for Google API key (primary - matches existing code)
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key:
            return LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=google_key,
                max_tokens=4000,
                temperature=0.1
            )
        
        # Check for OpenAI API key (fallback)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            return LLMConfig(
                provider="gpt-4o-mini",
                api_token=openai_key,
                max_tokens=4000,
                temperature=0.1
            )
        
        # Check for Anthropic API key (fallback)
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            return LLMConfig(
                provider="claude-3-haiku-20240307",
                api_token=anthropic_key,
                max_tokens=4000,
                temperature=0.1
            )
        
        logger.warning("No LLM API keys found in environment variables")
        return None
        
    except Exception as e:
        logger.error(f"Error getting LLM configuration: {e}")
        return None 