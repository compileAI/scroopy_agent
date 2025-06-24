"""
Test LLM ground truth extraction issues
"""

import asyncio
import logging
import sys
import os
import json
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    print(f"✅ Environment loaded from {env_path}")
except ImportError:
    print("⚠️ python-dotenv not installed")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_llm_config():
    """Test LLM configuration"""
    print("🔍 Testing LLM configuration...")
    
    try:
        from utils.llm_config import get_llm_config
        
        config = get_llm_config()
        if config:
            print(f"✅ LLM config found:")
            print(f"   Provider: {config.provider}")
            print(f"   Max tokens: {config.max_tokens}")
            print(f"   Temperature: {config.temperature}")
            print(f"   API token: {config.api_token[:10]}...{config.api_token[-10:]}")
            return config
        else:
            print("❌ No LLM configuration available")
            return None
            
    except Exception as e:
        print(f"❌ LLM config test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_crawl4ai_llm_extraction():
    """Test Crawl4AI LLM extraction directly"""
    print("\n🔍 Testing Crawl4AI LLM extraction...")
    
    try:
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai import LLMConfig, CrawlerRunConfig, AsyncWebCrawler
        
        # Test URL
        test_url = "https://www.wmagazine.com/culture/sydney-sweeney-cover-interview-photos-2025"
        
        # Create LLM strategy
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=os.getenv('GOOGLE_API_KEY')
            ),
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The main article title"},
                    "content": {"type": "string", "description": "Article content as plain text"},
                    "author": {"type": "string", "description": "Author name"},
                    "date": {"type": "string", "description": "Publication date"}
                },
                "required": ["title", "content"]
            },
            extraction_type="schema",
            instruction="Extract the main article title and content from this webpage. Return clean text without formatting.",
            extra_args={"temperature": 0.1, "max_tokens": 1000}
        )
        
        # Test extraction
        print(f"🧪 Testing extraction on: {test_url}")
        
        crawler = AsyncWebCrawler(verbose=True, headless=True)
        
        config = CrawlerRunConfig(
            extraction_strategy=llm_strategy,
            verbose=True
        )
        
        result = await crawler.arun(test_url, config=config)
        
        print(f"📊 Extraction result:")
        print(f"   Success: {result.success}")
        print(f"   Error: {result.error}")
        print(f"   Content length: {len(result.extracted_content) if result.extracted_content else 0}")
        
        if result.extracted_content:
            print(f"   Raw content type: {type(result.extracted_content)}")
            print(f"   Raw content preview: {str(result.extracted_content)[:200]}...")
            
            try:
                # Try to parse as JSON
                extracted_data = json.loads(result.extracted_content)
                print(f"   ✅ Parsed as JSON successfully")
                print(f"   Data type: {type(extracted_data)}")
                print(f"   Data keys: {list(extracted_data.keys()) if isinstance(extracted_data, dict) else 'Not a dict'}")
                
                if isinstance(extracted_data, dict):
                    print(f"   Title: {extracted_data.get('title', 'MISSING')}")
                    print(f"   Author: {extracted_data.get('author', 'MISSING')}")
                    print(f"   Content preview: {str(extracted_data.get('content', 'MISSING'))[:100]}...")
                
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON parsing failed: {e}")
        else:
            print(f"   ❌ No extracted content")
        
        # Test cleanup
        try:
            await crawler.aclose()
            print(f"   ✅ Crawler closed with aclose()")
        except AttributeError:
            try:
                await crawler.close()
                print(f"   ✅ Crawler closed with close()")
            except Exception as e:
                print(f"   ⚠️ Crawler cleanup failed: {e}")
        
    except Exception as e:
        print(f"❌ Crawl4AI LLM extraction test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_simple_llm_call():
    """Test simple LLM call to isolate the issue"""
    print("\n🔍 Testing simple LLM call...")
    
    try:
        # Test direct Google Generative AI
        print("🧪 Testing Google Generative AI directly...")
        
        try:
            import google.generativeai as genai
            
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                print("❌ No Google API key found")
                return
                
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            response = model.generate_content(
                "What is the capital of France? Respond with just the city name.",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=100,
                    temperature=0.1
                )
            )
            
            print(f"   ✅ Google Generative AI response: {response.text}")
            
        except ImportError:
            print("   ❌ google-generativeai not available")
        except Exception as e:
            print(f"   ❌ Google Generative AI test failed: {e}")
        
        # Test DSPy
        print("\n🧪 Testing DSPy...")
        
        try:
            import dspy
            
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                print("❌ No Google API key found")
                return
            
            # Configure DSPy
            lm = dspy.Google(
                model="gemini-2.0-flash",
                api_key=api_key,
                max_tokens=100,
                temperature=0.1
            )
            dspy.configure(lm=lm)
            
            # Simple prediction
            predict = dspy.Predict("question -> answer")
            response = predict(question="What is the capital of France? Respond with just the city name.")
            
            print(f"   ✅ DSPy response: {response.answer}")
            
        except ImportError:
            print("   ❌ dspy not available")
        except Exception as e:
            print(f"   ❌ DSPy test failed: {e}")
            
    except Exception as e:
        print(f"❌ Simple LLM call test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_discovery_function():
    """Test the news source discovery function"""
    print("\n🔍 Testing news source discovery...")
    
    try:
        from tools.discovery import discover_sources
        
        query = "AI research"
        print(f"🧪 Testing discovery with query: {query}")
        
        result = await discover_sources(query)
        print(f"📊 Discovery result type: {type(result)}")
        print(f"📊 Discovery result preview: {result[:200]}...")
        
        # Try to parse as JSON
        try:
            data = json.loads(result)
            print(f"   ✅ Parsed as JSON successfully")
            print(f"   Status: {data.get('status', 'MISSING')}")
            if data.get('status') == 'success':
                sources = data.get('sources', [])
                print(f"   Sources found: {len(sources)}")
                for i, source in enumerate(sources, 1):
                    print(f"      {i}. {source.get('name', 'MISSING')} - {source.get('url', 'MISSING')}")
            else:
                print(f"   Error: {data.get('error', 'MISSING')}")
                
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON parsing failed: {e}")
        
    except Exception as e:
        print(f"❌ Discovery test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    async def run_all_tests():
        config = await test_llm_config()
        if config:
            await test_simple_llm_call()
            await test_discovery_function()
            await test_crawl4ai_llm_extraction()
        else:
            print("❌ Cannot run tests without LLM configuration")
    
    asyncio.run(run_all_tests()) 