"""
News source discovery tool for Scroopy agent
"""

import json
import logging
import re
import os
from typing import List, Dict, Any

# Import rate limiting
from utils.rate_limiter import rate_limited, wait_for_rate_limit, get_rate_limiter_stats

logger = logging.getLogger(__name__)

def get_dspy_lm():
    """
    Get DSPy LM instance using available API keys.
    Returns a simple callable that uses the available LLM configuration.
    """
    try:
        from utils.llm_config import get_llm_config
        import json
        
        config = get_llm_config()
        if not config:
            logger.error("No LLM configuration available - missing API keys")
            return None
        
        # Import the appropriate library based on provider
        if config.provider.startswith("gemini"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=config.api_token)
                model = genai.GenerativeModel('gemini-2.0-flash')
                
                def llm_callable(prompt):
                    try:
                        response = model.generate_content(
                            prompt,
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=config.max_tokens,
                                temperature=config.temperature
                            )
                        )
                        return response.text
                    except Exception as e:
                        logger.error(f"Gemini API call failed: {e}")
                        raise e
                
                return llm_callable
                
            except ImportError:
                logger.warning("google-generativeai not available, falling back to dspy")
                pass
        
        # Fallback to dspy if available
        try:
            import dspy
            
            # Configure dspy with the available provider
            if config.provider.startswith("gemini"):
                dspy.configure(lm=dspy.Google(
                    model="gemini-2.0-flash",
                    api_key=config.api_token,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                ))
            elif config.provider.startswith("gpt"):
                dspy.configure(lm=dspy.OpenAI(
                    model=config.provider,
                    api_key=config.api_token,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                ))
            elif config.provider.startswith("claude"):
                dspy.configure(lm=dspy.Claude(
                    model=config.provider,
                    api_key=config.api_token,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                ))
            
            # Return DSPy LM callable
            def dspy_callable(prompt):
                try:
                    response = dspy.Predict("question -> answer")(question=prompt)
                    return response.answer
                except Exception as e:
                    logger.error(f"DSPy API call failed: {e}")
                    raise e
            
            return dspy_callable
            
        except ImportError:
            logger.error("Neither google-generativeai nor dspy available")
            return None
            
    except Exception as e:
        logger.error(f"Error setting up LLM: {e}")
        return None

@rate_limited
async def discover_sources(user_query: str) -> str:
    """
    Discover reputable news sources based on user's interest query.
    
    Args:
        user_query: User's description of news content they're interested in
        
    Returns:
        JSON string with discovered sources
    """
    try:
        logger.info(f"🔍 Discovering news sources for: '{user_query}'")
        print(f"🔍 TOOL: discover_sources - Finding sources for '{user_query}'")
        
        _dspy_lm = get_dspy_lm()
        if _dspy_lm is None:
            error_msg = "DSPy not initialized - GOOGLE_API_KEY required"
            logger.error(f"❌ {error_msg}")
            return json.dumps({"status": "error", "error": error_msg})
        
        # Very clear prompt for source discovery
        discovery_prompt = f"""
You are a news source discovery expert. Your task is to find 4-5 reputable, well-known news websites that regularly publish content about the user's area of interest.

USER'S INTEREST: "{user_query}"

REQUIREMENTS:
1. Only suggest major, established news websites (like CNN, BBC, Reuters, TechCrunch, etc.)
2. Sources must be in English
3. Sources must have a clear homepage with article links
4. Sources must regularly publish NEW articles (not just archives)
5. Focus on sources that are well-structured and scrapable

RESPONSE FORMAT:
Return ONLY a valid JSON array with exactly this structure:
[
  {{
    "url": "https://example.com",
    "name": "Example News",
    "description": "Brief description of what this source covers",
    "relevance": "Why this source matches the user's interest"
  }}
]

Do not include any other text, explanations, or formatting. Just the JSON array.
"""
        
        # Use DSPy to get the response
        response = _dspy_lm(discovery_prompt)
        
        # Parse and validate the response
        try:
            # Extract JSON from response
            response_text = response if isinstance(response, str) else str(response)
            
            # Try to find JSON in the response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            else:
                json_text = response_text
            
            sources = json.loads(json_text)
            
            if not isinstance(sources, list) or len(sources) == 0:
                raise ValueError("No sources returned")
            
            # Validate each source has required fields
            for source in sources:
                if not all(key in source for key in ['url', 'name', 'description']):
                    raise ValueError("Source missing required fields")
            
            result = {
                "status": "success",
                "user_query": user_query,
                "sources": sources[:3],  # Limit to 3 sources max
                "count": len(sources[:3])
            }
            
            logger.info(f"✅ Found {len(sources[:3])} sources for '{user_query}'")
            print(f"✅ TOOL SUCCESS: Found {len(sources[:3])} sources")
            for i, source in enumerate(sources[:3], 1):
                print(f"   {i}. {source['name']} - {source['url']}")
            
            return json.dumps(result)
            
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to parse LLM response as valid JSON: {e}"
            logger.error(f"❌ {error_msg}")
            print(f"❌ TOOL ERROR: {error_msg}")
            print(f"   Raw response: {response_text[:200]}...")
            
            return json.dumps({
                "status": "error",
                "error": error_msg,
                "raw_response": response_text[:500]
            })
            
    except Exception as e:
        error_msg = f"Error discovering sources: {str(e)}"
        logger.error(f"❌ {error_msg}")
        print(f"❌ TOOL ERROR: {error_msg}")
        return json.dumps({"status": "error", "error": error_msg}) 
