"""
DSPy signatures for Scroopy agent
"""

import dspy

class ScroopyAgentSignature(dspy.Signature):
    """
    Intelligent news source discovery and integration agent.
    
    Takes a user's news interest query and discovers reputable sources,
    validates their extraction schemas, and adds successful sources to the database.
    """
    
    user_query: str = dspy.InputField(
        desc="User's query describing what kind of news content they're interested in (e.g., 'technology news', 'sports updates', 'financial markets')"
    )
    
    result: str = dspy.OutputField(
        desc="Confirmation message detailing which news sources were successfully discovered, validated, and added to the database"
    ) 