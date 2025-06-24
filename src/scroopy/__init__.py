"""
Scroopy Package - Core agent functionality
"""

from .agent import ScroopyAgent
from .config import setup_dspy_gemini

__all__ = [
    "ScroopyAgent",
    "setup_dspy_gemini",
] 
