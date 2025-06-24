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

```bash
# Run the agent with a topic
python main.py --query "AI research" --pretty

# Save results to file
python main.py --query "Canadian politics" --output results.json --pretty

# Or run the agent directly
cd src
python run_structured_agent.py
```

### Programmatic Usage

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

## Requirements

- Python 3.8+
- OpenAI API key (required for schema generation)
- Optional: DSPy API key for enhanced AI features

## Project Structure

```
scroopy-agent/
├── main.py                    # CLI entry point
├── src/
│   ├── structured_agent.py   # Main agent logic
│   ├── tools/                # Core tools
│   └── utils/                # Support utilities
├── requirements.txt          # Dependencies
└── .env.example             # Environment template
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
