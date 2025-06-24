# 🧪 Scroopy Agent Test Suite

This directory contains diagnostic tests to identify and fix issues with the Scroopy Agent.

## 🚀 Quick Start

1. **Install dependencies (if not already done):**
   ```bash
   pip install google-generativeai>=0.3.0
   ```

2. **Make sure your `.env` file has the required API key:**
   ```bash
   GOOGLE_API_KEY=your_google_api_key_here
   ```

3. **Run all diagnostic tests:**
   ```bash
   cd tests
   python run_tests.py
   ```

## 📋 Test Files

### `test_crawler_cleanup.py`
- **Purpose:** Diagnose AsyncWebCrawler cleanup method issues
- **What it tests:** 
  - Discovers available crawler methods
  - Tests different cleanup approaches (`aclose`, `close`, `__aexit__`)
  - Validates environment variable loading

### `test_llm_ground_truth.py`
- **Purpose:** Diagnose LLM ground truth extraction issues
- **What it tests:**
  - LLM configuration setup
  - Direct Google Generative AI calls
  - DSPy integration
  - Crawl4AI LLM extraction strategy
  - News source discovery function

### `run_tests.py`
- **Purpose:** Master test runner
- **What it does:**
  - Orchestrates all diagnostic tests
  - Provides structured output for troubleshooting
  - Includes mini integration test

## 🔍 Common Issues & Fixes

### Issue 1: `'AsyncWebCrawler' object has no attribute 'aclose'`
**Diagnosis:** Run `python test_crawler_cleanup.py`
**Fix:** The crawler manager now tries multiple cleanup methods automatically

### Issue 2: `NO_TITLE_EXTRACTED` in ground truth
**Diagnosis:** Run `python test_llm_ground_truth.py`  
**Fix:** Check LLM configuration and API key setup

### Issue 3: Windows asyncio resource warnings
**Diagnosis:** Look for "Event loop is closed" errors
**Fix:** Improved cleanup handlers in crawler manager

## 📊 Interpreting Test Results

### ✅ Success Indicators
- LLM configuration found
- API calls working
- Crawler methods discovered
- JSON parsing successful

### ❌ Failure Indicators  
- Missing API keys
- Import errors
- Network timeouts
- JSON parsing failures

## 🛠️ Development Workflow

1. **Run tests** before making changes
2. **Identify specific failures** from test output
3. **Apply targeted fixes** based on diagnostics
4. **Re-run tests** to verify fixes
5. **Test integration** with main application

## 📝 Adding New Tests

Create new test files following the pattern:
```python
# tests/test_new_feature.py
import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

async def test_new_feature():
    """Test description"""
    # Your test code here
    pass

if __name__ == "__main__":
    asyncio.run(test_new_feature())
```

Then add it to `run_tests.py` to include in the main test suite. 