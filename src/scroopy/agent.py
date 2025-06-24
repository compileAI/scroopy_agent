"""
Main Scroopy Agent implementation
"""

import logging
import dspy
from .config import get_dspy_lm
from .signatures import ScroopyAgentSignature

logger = logging.getLogger(__name__)

class ScroopyAgent(dspy.Module):
    """
    Scroopy - The Intelligent Web Scraping Agent
    
    Discovers news sources based on user interests, validates their extraction schemas
    against LLM ground truth, and integrates successful sources into the database.
    """
    
    def __init__(self):
        super().__init__()
        logger.info("🤖 Initializing Scroopy Agent...")
        
        try:
            # Initialize DSPy with Gemini
            lm = get_dspy_lm()
            if not lm:
                raise ValueError("Cannot initialize Scroopy - DSPy/Gemini not available")
            
            # Import tool functions - do this inside __init__ to avoid circular imports
            import sys
            from pathlib import Path
            
            # Add the src directory to path for tool imports
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            
            try:
                from tools.discovery import discover_sources
                from tools.link_schema_generator import generate_link_schema  
                from tools.article_schema_generator import generate_validated_article_schema
                from tools.web_fetcher import fetch_webpage
                from tools.supabase_writer import write_crawl_source
                print("✅ Successfully imported all 5 real tools")
                
                # Create Tool objects with proper descriptions
                from dspy import Tool
                
                self.tools = [
                    Tool(
                        discover_sources,
                        name="discover_sources",
                        desc="Discover 3-5 relevant news sources for a given topic. Input: topic string. Output: JSON with discovered sources."
                    ),
                    Tool(
                        generate_link_schema,  
                        name="generate_link_schema",
                        desc="Generate CSS extraction schema for finding article links on a homepage. Input: base_url. Output: JSON with link extraction schema."
                    ),
                    Tool(
                        generate_validated_article_schema,
                        name="generate_validated_article_schema", 
                        desc="Generate and validate CSS schema for extracting article content. Input: base_url, sample_urls list. Output: JSON with validated article schema."
                    ),
                    Tool(
                        fetch_webpage,
                        name="fetch_webpage",
                        desc="Fetch webpage content for analysis. Input: url. Output: JSON with webpage content and metadata."
                    ),
                    Tool(
                        write_crawl_source,
                        name="write_crawl_source",
                        desc="Write a validated CrawlSource to Supabase database. Only writes sources with validated schemas. Input: source_data dict. Output: JSON with write status."
                    )
                ]
                
                # Initialize ReAct agent with all 5 tools
                self.react = dspy.ReAct(
                    ScroopyAgentSignature,
                    tools=self.tools,
                    max_iters=20
                )
                
            except ImportError as e:
                print(f"❌ Error importing tools: {e}")
                # Create dummy tools for testing
                self.tools = [self._create_dummy_tool(f"tool_{i}") for i in range(5)]
                print("⚠️ Using dummy tools - real functionality not available")
                
                # Initialize ReAct with dummy tools
                self.react = dspy.ReAct(
                    ScroopyAgentSignature,
                    tools=self.tools,
                    max_iters=20
                )
            
            logger.info("✅ Scroopy Agent initialized successfully with 5 tools")
        except Exception as e:
            logger.error(f"❌ Error initializing Scroopy Agent: {e}")
            raise
    
    def _create_dummy_tool(self, name: str):
        """Create a dummy tool for testing when real tools aren't available"""
        def dummy_func(*args, **kwargs):
            return f"Dummy result from {name}"
        
        # Try to import Tool, fallback if not available
        try:
            from dspy import Tool
            return Tool(dummy_func, name=name, desc=f"Dummy tool {name}")
        except ImportError:
            return dummy_func
    
    def forward(self, user_query: str) -> str:
        """
        Main entry point for Scroopy agent (synchronous version)
        
        Args:
            user_query: User's description of news content they're interested in
            
        Returns:
            Confirmation of sources added to database
        """
        logger.info(f"🎯 Scroopy processing user query: '{user_query}'")
        
        # Execute the ReAct workflow (synchronous)
        result = self.react(user_query=user_query)
        
        logger.info("🏁 Scroopy workflow completed")
        return result.result if hasattr(result, 'result') else str(result)
    
    async def aforward(self, user_query: str) -> str:
        """
        Async entry point for Scroopy agent (for async tool support)
        
        Args:
            user_query: User's description of news content they're interested in
            
        Returns:
            Confirmation of sources added to database
        """
        logger.info(f"🎯 Scroopy processing user query (async): '{user_query}'")
        
        # Execute the ReAct workflow (asynchronous - handles both sync and async tools)
        result = await self.react.acall(user_query=user_query)
        
        logger.info("🏁 Scroopy async workflow completed")
        return result.result if hasattr(result, 'result') else str(result) 