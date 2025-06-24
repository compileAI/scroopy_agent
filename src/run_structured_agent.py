#!/usr/bin/env python3
"""
Test script for the Structured Scroopy Agent
"""

import asyncio
import json
import logging

# Import the structured agent
from structured_agent import run_structured_agent

async def main():
    """Main function to run the structured agent"""
    print("🤖 Starting Structured Scroopy Agent...")
    
    # User query
    query = "AI Deals and Investments"
    print(f"🎯 Query: {query}")
    
    # Run the structured agent
    try:
        result = await run_structured_agent(query)
        
        print("\n" + "="*80)
        print("🏁 STRUCTURED SCROOPY AGENT RESULT:")
        print("="*80)
        
        # Pretty print the result
        if result.get("status") == "success":
            print(f"✅ Status: {result['status']}")
            print(f"📊 Sources Processed: {result['sources_processed']}")
            
            print("\n" + result["summary"])
            
            # Show detailed results for each source
            print("\n📋 Detailed Results:")
            print("-" * 40)
            
            for i, source in enumerate(result["sources"], 1):
                print(f"\n{i}. {source['name']} ({source['status']})")
                print(f"   URL: {source['url']}")
                
                if source.get('link_schema'):
                    selector = source['link_schema'].get('baseSelector', 'N/A')
                    print(f"   Link Schema: {selector}")
                
                if source.get('sample_urls'):
                    print(f"   Sample URLs ({len(source['sample_urls'])}):")
                    for j, url in enumerate(source['sample_urls'], 1):
                        print(f"      {j}. {url}")
                
                if source.get('validation_score') is not None:
                    print(f"   Validation Score: {source['validation_score']:.1f}%")
        else:
            print(f"❌ Status: {result['status']}")
            print(f"❌ Error: {result.get('message', 'Unknown error')}")
        
        print("="*80)
        
    except Exception as e:
        print(f"❌ Error running structured agent: {e}")
        logging.exception("Structured agent error")

if __name__ == "__main__":
    asyncio.run(main()) 