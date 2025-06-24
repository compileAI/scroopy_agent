"""
Scroopy - Intelligent Web Scraping Agent

A DSPy ReAct-based agent that discovers news sources, generates extraction schemas,
validates them against LLM ground truth, and integrates successful sources.
"""

__version__ = "0.1.0"
__author__ = "Scroopy Development Team"

# Main exports
from .scroopy.agent import ScroopyAgent
from .scroopy.config import setup_dspy_gemini

__all__ = [
    "ScroopyAgent",
    "setup_dspy_gemini",
] 
