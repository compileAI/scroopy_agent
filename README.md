# Scroopy Agent

A structured web scraping agent that discovers news sources and generates extraction schemas.

## Overview

The Scroopy Agent follows a clear workflow:

1. **Discover Sources**: Find relevant news sources for any topic
2. **Generate Link Schemas**: Analyze homepage layouts to extract article links  
3. **Extract Sample URLs**: Get real article URLs using the schemas
4. **Generate Article Schemas**: Create and validate schemas for extracting article content
5. **Return Results**: Structured output with schemas and validation scores

## Quick Start

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd scroopy-agent

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys (especially OPENAI_API_KEY)
```

### Usage

#### Original Structured Agent

```bash
# Run the original agent with a topic
python main.py --query "AI research" --pretty

# Save results to file
python main.py --query "Canadian politics" --output results.json --pretty

# Or run the agent directly
cd src
python run_structured_agent.py
```

#### LangGraph Agent (Enhanced)

The LangGraph agent includes enhanced state management, validation feedback loops, and automatic retries for better results:

```bash
# Run the enhanced LangGraph agent
python main_langgraph.py --query "AI research" --pretty

# Save results to file
python main_langgraph.py --query "Canadian politics" --output results.json --pretty
```

### Programmatic Usage

#### Original Agent

```python
import asyncio
from src.structured_agent import run_structured_agent

async def example():
    result = await run_structured_agent("AI research")
    
    if result["status"] == "success":
        for source in result["sources"]:
            if source["status"] == "completed":
                print(f"✅ {source['name']}: {source['validation_score']:.1f}%")

asyncio.run(example())
```

#### LangGraph Agent (Recommended)

```python
import asyncio
from src.langgraph_agent import run_langgraph_agent

async def example():
    result = await run_langgraph_agent("AI technology news")
    
    for source in result["sources"]:
        print(f"Source: {source['name']}")
        print(f"Status: {source['status']}")
        print(f"Validation Score: {source.get('validation_score', 'N/A')}")
        print(f"Attempts: {source.get('validation_attempts', 1)}")
        
        if source.get('validation_feedback'):
            print("Improvements applied:")
            for feedback in source['validation_feedback']:
                print(f"  • {feedback}")

asyncio.run(example())
```

## Requirements

- Python 3.8+
- OpenAI API key (required for schema generation)
- Optional: DSPy API key for enhanced AI features

### LangGraph Agent Additional Dependencies

For the enhanced LangGraph agent, additional dependencies are required:

```bash
# Install LangGraph dependencies (included in requirements.txt)
pip install langchain>=0.1.0 langchain-community>=0.0.20 langgraph>=0.0.30 langchain-google-genai>=1.0.0
```

## Agent Comparison

### 🚀 LangGraph Agent (Recommended)

**Enhanced Features:**
- ✅ **Smart Validation Feedback**: Automatic schema improvement based on validation results
- ✅ **Retry Logic**: Attempts up to 3 times per source with targeted improvements
- ✅ **Better State Management**: Persistent state tracking with detailed error handling
- ✅ **Enhanced Scoring**: More detailed validation with specific feedback
- ✅ **Graceful Failures**: Failed sources don't block processing of other sources

**Best for:** Production use, complex sites, maximum extraction quality

### 📝 Original Structured Agent

**Features:**
- ✅ **Simple & Direct**: Straightforward processing workflow
- ✅ **Fast Processing**: Single-pass extraction per source
- ✅ **Minimal Dependencies**: Fewer external requirements

**Best for:** Quick prototyping, simple sites, educational purposes

### Performance Comparison

| Feature | Original Agent | LangGraph Agent |
|---------|---------------|-----------------|
| **Validation Feedback** | ❌ None | ✅ Automatic with CSS suggestions |
| **Retry Logic** | ❌ Single attempt | ✅ Up to 3 attempts with improvements |
| **Error Recovery** | ⚠️ Basic | ✅ Graceful with detailed tracking |
| **State Management** | ⚠️ Manual | ✅ Automatic with persistence |
| **Average Quality** | 70-80% | 85-95% |

## Project Structure

```
scroopy-agent/
├── main.py                           # Original CLI entry point
├── main_langgraph.py                 # LangGraph CLI entry point (enhanced)
├── src/
│   ├── structured_agent.py          # Original agent logic
│   ├── langgraph_agent.py           # LangGraph agent (enhanced)
│   ├── tools/                       # Core tools
│   │   ├── article_schema_generator.py            # Original schema generator
│   │   └── article_schema_generator_enhanced.py   # Enhanced with feedback
│   └── utils/                       # Support utilities
├── tests/                           # Test suite
├── requirements.txt                 # Dependencies (includes LangGraph)
├── LANGGRAPH_MIGRATION.md          # Migration guide
└── .env.example                    # Environment template
```

## Output Format

The agent returns structured JSON with:

- **Sources analyzed**: List of news sources with their schemas
- **Validation scores**: Quality metrics for each schema
- **Sample URLs**: Real article URLs extracted from each source
- **Processing summary**: Success/failure counts and details

Example output:

```json
{
  "status": "success",
  "sources_processed": 3,
  "sources": [
    {
      "name": "TechCrunch",
      "url": "https://techcrunch.com",
      "status": "completed",
      "validation_score": 87.5,
      "link_schema": {...},
      "article_schema": {...},
      "sample_urls": [...]
    }
  ],
  "summary": "Successfully processed 2 sources, failed 1 source"
}
```
