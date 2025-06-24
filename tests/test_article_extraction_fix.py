"""
Test to specifically address the article extraction issues seen in the logs
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
except ImportError:
    pass

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_specific_w_magazine_extraction():
    """Test the specific W Magazine URL that had issues"""
    print("🔍 Testing specific W Magazine extraction that failed...")
    
    test_url = "https://www.wmagazine.com/culture/sydney-sweeney-cover-interview-photos-2025"
    
    try:
        from tools.article_schema_generator import extract_article_with_llm
        
        print(f"🧪 Testing LLM extraction on: {test_url}")
        
        result = await extract_article_with_llm(test_url)
        
        print(f"📊 Extraction result:")
        print(f"   Type: {type(result)}")
        
        if result is None:
            print("   ❌ Result is None - extraction failed completely")
            return False
        elif isinstance(result, dict):
            print("   ✅ Result is a dictionary")
            print(f"   Keys: {list(result.keys())}")
            
            title = result.get('title', 'MISSING')
            content = result.get('content', 'MISSING')
            author = result.get('author', 'MISSING')
            date = result.get('date_published', 'MISSING')
            
            print(f"   Title: {title}")
            print(f"   Author: {author}")
            print(f"   Date: {date}")
            print(f"   Content length: {len(content) if content != 'MISSING' else 0}")
            print(f"   Content preview: {content[:150] if content != 'MISSING' else 'NONE'}...")
            
            # Check for the specific issues we saw
            if title == "NO_TITLE_EXTRACTED":
                print("   ❌ Found NO_TITLE_EXTRACTED issue")
                return False
            elif not title or title == 'MISSING':
                print("   ❌ Title is missing")
                return False
            elif not content or content == 'MISSING' or content == "NO_CONTENT_EXTRACTED":
                print("   ❌ Content is missing or empty")
                return False
            else:
                print("   ✅ Extraction appears successful")
                return True
        else:
            print(f"   ❌ Unexpected result type: {type(result)}")
            print(f"   Value: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_llm_extraction_strategy_directly():
    """Test the LLM extraction strategy directly to isolate the issue"""
    print("\n🔍 Testing LLM extraction strategy directly...")
    
    try:
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai import LLMConfig, CrawlerRunConfig, AsyncWebCrawler
        
        test_url = "https://www.wmagazine.com/culture/sydney-sweeney-cover-interview-photos-2025"
        api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            print("❌ No Google API key found")
            return False
        
        # Create a simpler, more focused extraction strategy
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=api_key
            ),
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Main article headline"},
                    "content": {"type": "string", "description": "Full article text"}
                },
                "required": ["title", "content"]
            },
            extraction_type="schema",
            instruction="""Extract the main article title and content from this webpage.
            
REQUIREMENTS:
- title: Find the main article headline (usually in h1 tags)
- content: Extract the complete article text, all paragraphs

Return only valid JSON with the title and content fields.""",
            extra_args={"temperature": 0.1, "max_tokens": 2000}
        )
        
        print(f"🧪 Testing direct LLM strategy on: {test_url}")
        
        crawler = AsyncWebCrawler(verbose=False, headless=True)
        
        config = CrawlerRunConfig(
            extraction_strategy=llm_strategy,
            verbose=False
        )
        
        result = await crawler.arun(test_url, config=config)
        
        print(f"📊 Direct extraction result:")
        print(f"   Success: {result.success}")
        
        if result.error:
            print(f"   Error: {result.error}")
        
        if result.extracted_content:
            print(f"   Content type: {type(result.extracted_content)}")
            print(f"   Content length: {len(result.extracted_content)}")
            print(f"   Raw content: {result.extracted_content[:300]}...")
            
            try:
                # Parse the JSON
                data = json.loads(result.extracted_content)
                print(f"   ✅ JSON parsing successful")
                print(f"   Title: {data.get('title', 'MISSING')}")
                print(f"   Content length: {len(data.get('content', ''))}")
                print(f"   Content preview: {data.get('content', '')[:150]}...")
                
                success = True
                if not data.get('title'):
                    print("   ❌ No title extracted")
                    success = False
                if not data.get('content'):
                    print("   ❌ No content extracted")
                    success = False
                
                return success
                
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON parsing failed: {e}")
                return False
        else:
            print(f"   ❌ No extracted content")
            return False
        
        # Try to cleanup
        try:
            # Test different cleanup methods
            if hasattr(crawler, 'close'):
                if asyncio.iscoroutinefunction(crawler.close):
                    await crawler.close()
                else:
                    crawler.close()
                print(f"   ✅ Crawler cleaned up with close()")
            else:
                print(f"   ⚠️ No close method found on crawler")
        except Exception as cleanup_error:
            print(f"   ⚠️ Cleanup failed: {cleanup_error}")
        
    except Exception as e:
        print(f"❌ Direct LLM strategy test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_choices_attribute_error():
    """Test to identify the 'str' object has no attribute 'choices' error"""
    print("\n🔍 Testing for 'choices' attribute error...")
    
    try:
        # This error suggests there's an issue with how the LLM response is being processed
        # Let's test a simple DSPy call to see if we can reproduce it
        
        import dspy
        
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            print("❌ No Google API key found")
            return False
        
        # Configure DSPy
        lm = dspy.Google(
            model="gemini-2.0-flash",
            api_key=api_key,
            max_tokens=100,
            temperature=0.1
        )
        dspy.configure(lm=lm)
        
        # Test a simple prediction
        predict = dspy.Predict("question -> answer")
        
        print(f"🧪 Testing simple DSPy prediction...")
        response = predict(question="What is 2+2? Answer with just the number.")
        
        print(f"📊 DSPy response:")
        print(f"   Type: {type(response)}")
        print(f"   Value: {response}")
        
        # Check if response has 'answer' attribute
        if hasattr(response, 'answer'):
            print(f"   Answer: {response.answer}")
            print(f"   Answer type: {type(response.answer)}")
            
            # Check if the answer has 'choices' attribute (this might be the issue)
            if hasattr(response.answer, 'choices'):
                print(f"   ❌ Found 'choices' attribute on answer - this might be the problem")
                print(f"   Choices: {response.answer.choices}")
            else:
                print(f"   ✅ No 'choices' attribute on answer")
        else:
            print(f"   ❌ No 'answer' attribute on response")
        
        # Check the raw response object
        print(f"   Raw response attributes: {[attr for attr in dir(response) if not attr.startswith('_')]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Choices attribute test failed: {e}")
        # Check if this is the specific error we're looking for
        if "'str' object has no attribute 'choices'" in str(e):
            print(f"   🎯 Found the specific 'choices' error!")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    async def run_focused_tests():
        print("🎯 FOCUSED ARTICLE EXTRACTION TESTS")
        print("="*80)
        
        # Test 1: Specific URL that had issues
        success1 = await test_specific_w_magazine_extraction()
        
        # Test 2: Direct LLM strategy
        success2 = await test_llm_extraction_strategy_directly()
        
        # Test 3: Choices attribute error
        success3 = await test_choices_attribute_error()
        
        print("\n" + "="*80)
        print("🏁 FOCUSED TEST RESULTS")
        print("="*80)
        print(f"W Magazine extraction: {'✅ PASS' if success1 else '❌ FAIL'}")
        print(f"Direct LLM strategy: {'✅ PASS' if success2 else '❌ FAIL'}")
        print(f"Choices error test: {'✅ PASS' if success3 else '❌ FAIL'}")
        
        overall_success = success1 and success2 and success3
        print(f"\nOverall: {'🎉 ALL TESTS PASSED' if overall_success else '🔧 ISSUES FOUND - Review output above'}")
    
    asyncio.run(run_focused_tests()) 