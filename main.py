#!/usr/bin/env python3
"""
Simple Scroopy Agent Entry Point
Focused on the structured agent workflow
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("⚠️ python-dotenv not installed - environment variables may not be loaded")

from structured_agent import run_structured_agent


async def main():
    """Command line interface for the Structured Scroopy Agent."""
    parser = argparse.ArgumentParser(description="Scroopy Agent - Structured Web Scraping")
    parser.add_argument("--query", "-q", required=True, help="Query for news source discovery (e.g., 'AI research', 'Canadian politics')")
    parser.add_argument("--output", "-o", help="Output file path (optional)")
    parser.add_argument("--pretty", "-p", action="store_true", help="Pretty print JSON output")
    
    args = parser.parse_args()
    
    print(f"🤖 Scroopy Agent Starting")
    print(f"   📥 Query: {args.query}")
    
    try:
        # Run the structured agent
        result = await run_structured_agent(args.query)
        
        # Format output
        if args.pretty:
            output = json.dumps(result, indent=2)
        else:
            output = json.dumps(result)
        
        # Save or print output
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"✅ Result saved to: {args.output}")
        else:
            print("\n" + "="*80)
            print("🏁 STRUCTURED SCROOPY AGENT RESULT:")
            print("="*80)
            print(output)
        
        # Exit with appropriate code
        sys.exit(0 if result["status"] == "success" else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
