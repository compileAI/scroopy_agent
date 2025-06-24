"""
Test crawler cleanup and method discovery
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_crawler_methods():
    """Test to discover the correct AsyncWebCrawler cleanup method"""
    print("🔍 Testing AsyncWebCrawler methods...")
    
    try:
        from crawl4ai import AsyncWebCrawler
        
        # Create a crawler instance
        crawler = AsyncWebCrawler(verbose=False, headless=True)
        
        # List all available methods
        print(f"📋 AsyncWebCrawler available methods:")
        methods = [method for method in dir(crawler) if not method.startswith('_')]
        for method in sorted(methods):
            print(f"   - {method}")
        
        # Check specifically for close-related methods
        close_methods = [method for method in methods if 'close' in method.lower()]
        print(f"\n🔍 Close-related methods found: {close_methods}")
        
        # Check for cleanup/shutdown methods
        cleanup_methods = [method for method in methods if any(word in method.lower() for word in ['close', 'shutdown', 'stop', 'cleanup', 'exit'])]
        print(f"🧹 Cleanup-related methods found: {cleanup_methods}")
        
        # Try to find the correct method by checking callable attributes
        print(f"\n🎯 Testing cleanup methods:")
        
        for method_name in cleanup_methods:
            method = getattr(crawler, method_name, None)
            if method and callable(method):
                print(f"   ✅ {method_name}() - callable")
                
                # Check if it's async
                import inspect
                if inspect.iscoroutinefunction(method):
                    print(f"      🔄 {method_name}() is async")
                else:
                    print(f"      🔄 {method_name}() is sync")
            else:
                print(f"   ❌ {method_name} - not callable")
        
        # Test the most likely candidates
        print(f"\n🧪 Testing cleanup methods:")
        
        test_methods = ['aclose', 'close', 'shutdown', 'stop', '__aexit__']
        
        for method_name in test_methods:
            if hasattr(crawler, method_name):
                method = getattr(crawler, method_name)
                if callable(method):
                    try:
                        print(f"   🧪 Testing {method_name}()...")
                        
                        import inspect
                        if inspect.iscoroutinefunction(method):
                            # It's async
                            if method_name == '__aexit__':
                                await method(None, None, None)
                            else:
                                await method()
                            print(f"   ✅ {method_name}() worked (async)")
                        else:
                            # It's sync
                            if method_name == '__aexit__':
                                method(None, None, None)
                            else:
                                method()
                            print(f"   ✅ {method_name}() worked (sync)")
                        
                        # Create a new crawler for next test
                        crawler = AsyncWebCrawler(verbose=False, headless=True)
                        
                    except Exception as e:
                        print(f"   ❌ {method_name}() failed: {e}")
            else:
                print(f"   ❌ {method_name} not found")
        
        # Final cleanup attempt
        try:
            if hasattr(crawler, 'close'):
                await crawler.close() if inspect.iscoroutinefunction(crawler.close) else crawler.close()
                print(f"   ✅ Final cleanup with close() successful")
        except Exception as e:
            print(f"   ⚠️ Final cleanup failed: {e}")
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_environment():
    """Test environment setup"""
    print("🔍 Testing environment setup...")
    
    # Check if .env is loaded
    print(f"📋 Environment variables:")
    google_key = os.getenv('GOOGLE_API_KEY')
    print(f"   GOOGLE_API_KEY: {'✅ Set' if google_key else '❌ Missing'}")
    
    if google_key:
        print(f"   Key preview: {google_key[:10]}...{google_key[-10:]}")

if __name__ == "__main__":
    asyncio.run(test_crawler_methods())
    asyncio.run(test_environment()) 