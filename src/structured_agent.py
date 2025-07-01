"""
Structured Scroopy Agent - Sequential workflow for news source processing
"""

import json
import logging
import asyncio
from typing import List, Dict, Any
from dataclasses import dataclass

# Import tools
from tools.discovery import discover_sources
from tools.link_schema_generator import generate_link_schema
from tools.url_extractor import extract_urls_with_schema
from tools.article_schema_generator import generate_validated_article_schema

# Import crawler manager and rate limiting
from utils.crawler_manager import close_crawler
from utils.rate_limiter import get_rate_limiter_stats, reset_rate_limiter

# Import Supabase writer
from tools.supabase_writer import write_crawl_source

logger = logging.getLogger(__name__)

@dataclass
class NewsSource:
    """Data structure for a news source"""
    name: str
    url: str
    link_schema: Dict[str, Any] = None
    sample_urls: List[str] = None
    article_schema: Dict[str, Any] = None
    validation_score: float = None
    status: str = "pending"  # pending, processing, completed, failed

class StructuredScroopyAgent:
    """
    Structured agent that processes news sources sequentially following a clear workflow
    
    Workflow for each source:
    1. Generate link schema
    2. Extract real sample URLs using the schema
    3. Generate and validate article schema using real URLs
    4. Store results
    """
    
    def __init__(self):
        logger.info("🏗️ Initializing Structured Scroopy Agent")
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Main entry point that processes a query through the complete workflow
        
        Args:
            query: User query for news source discovery
            
        Returns:
            Dictionary with processed sources and results
        """
        logger.info(f"🎯 Processing query: {query}")
        
        # Show initial rate limiting stats
        initial_stats = get_rate_limiter_stats()
        logger.info(f"📊 Starting with rate limiter: {initial_stats['requests_in_last_minute']}/{initial_stats['requests_per_minute_limit']} requests in last minute")
        
        try:
            # Step 1: Discover news sources
            logger.info("📡 Step 1: Discovering news sources...")
            sources = await self._discover_sources(query)
            
            if not sources:
                return {
                    "status": "error",
                    "message": "No news sources discovered",
                    "sources": []
                }
            
            logger.info(f"✅ Discovered {len(sources)} sources")
            
            # Step 2: Process each source sequentially
            results = []
            for i, source in enumerate(sources, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"🏭 Processing Source {i}/{len(sources)}: {source.name}")
                logger.info(f"{'='*60}")
                
                source.status = "processing"
                processed_source = await self._process_single_source(source)
                results.append(processed_source)
                
                logger.info(f"✅ Completed {source.name} (Status: {processed_source.status})")
            
            # Step 3: Generate summary
            summary = self._generate_summary(results)
            
            # Show final rate limiting stats
            final_stats = get_rate_limiter_stats()
            logger.info(f"📊 Completed with rate limiter: {final_stats['requests_in_last_minute']}/{final_stats['requests_per_minute_limit']} requests in last minute")
            logger.info(f"📊 Total failures during run: {final_stats['consecutive_failures']}")
            
            return {
                "status": "success",
                "query": query,
                "sources_processed": len(results),
                "sources": [self._source_to_dict(s) for s in results],
                "summary": summary,
                "rate_limiter_stats": final_stats
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing query: {e}")
            return {
                "status": "error",
                "message": f"Processing failed: {str(e)}",
                "sources": []
            }
        finally:
            # Always cleanup
            try:
                await close_crawler()
                logger.info("🧹 Crawler resources cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Cleanup warning: {e}")
    
    async def _discover_sources(self, query: str) -> List[NewsSource]:
        """Step 1: Discover news sources for the query"""
        try:
            result = await discover_sources(query)
            result_data = json.loads(result)
            
            if result_data.get("status") != "success":
                logger.error(f"❌ Source discovery failed: {result_data.get('error', 'Unknown error')}")
                return []
            
            sources = []
            for source_data in result_data.get("sources", []):
                source = NewsSource(
                    name=source_data.get("name", "Unknown"),
                    url=source_data.get("url", "")
                )
                sources.append(source)
                logger.info(f"   📰 {source.name} - {source.url}")
            
            return sources
            
        except Exception as e:
            logger.error(f"❌ Error discovering sources: {e}")
            return []
    
    async def _process_single_source(self, source: NewsSource) -> NewsSource:
        """
        Process a single news source through the complete workflow
        
        Args:
            source: NewsSource object to process
            
        Returns:
            Updated NewsSource object with results
        """
        try:
            # Step 2a: Generate link schema
            logger.info(f"🔗 Step 2a: Generating link schema for {source.name}...")
            link_schema_result = await self._generate_link_schema(source)
            
            if not link_schema_result:
                source.status = "failed"
                return source
            
            # Step 2b: Extract real sample URLs
            logger.info(f"🎯 Step 2b: Extracting sample URLs for {source.name}...")
            sample_urls_result = await self._extract_sample_urls(source)
            
            if not sample_urls_result:
                source.status = "failed"
                return source
            
            # Step 2c: Generate article schema with real URLs
            logger.info(f"📰 Step 2c: Generating article schema for {source.name}...")
            article_schema_result = await self._generate_article_schema(source)
            
            # Check both generation success AND validation score
            if article_schema_result and source.validation_score is not None and source.validation_score >= 80.0:
                source.status = "completed"
                logger.info(f"✅ Source completed with validation score: {source.validation_score:.1f}%")
            elif article_schema_result and source.validation_score is not None:
                source.status = "failed"
                logger.warning(f"❌ Source failed due to low validation score: {source.validation_score:.1f}% (required: ≥80%)")
            else:
                source.status = "failed"
                logger.error("❌ Source failed - no article schema generated or validation failed")
            
            return source
            
        except Exception as e:
            logger.error(f"❌ Error processing {source.name}: {e}")
            source.status = "failed"
            return source
    
    async def _generate_link_schema(self, source: NewsSource) -> bool:
        """Generate link extraction schema for a source"""
        try:
            result = await generate_link_schema(source.url)
            result_data = json.loads(result)
            
            if result_data.get("status") == "success":
                source.link_schema = result_data.get("schema")
                logger.info(f"   ✅ Link schema generated: {source.link_schema.get('baseSelector', 'Unknown')}")
                return True
            else:
                logger.error(f"   ❌ Link schema generation failed: {result_data.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Link schema error: {e}")
            return False
    
    async def _extract_sample_urls(self, source: NewsSource) -> bool:
        """Extract real sample URLs using the generated link schema"""
        try:
            if not source.link_schema:
                logger.error("   ❌ No link schema available for URL extraction")
                return False
            
            # Extract up to 5 sample URLs
            result = await extract_urls_with_schema(
                source.url, 
                json.dumps(source.link_schema), 
                max_urls=5
            )
            result_data = json.loads(result)
            
            if result_data.get("status") == "success":
                urls = result_data.get("urls", [])
                if len(urls) >= 2:  # Need at least 2 URLs for validation
                    source.sample_urls = urls
                    logger.info(f"   ✅ Extracted {len(urls)} sample URLs")
                    for i, url in enumerate(urls, 1):
                        logger.info(f"      {i}. {url}")
                    return True
                else:
                    logger.warning(f"   ⚠️ Only extracted {len(urls)} URLs, need at least 2")
                    return False
            else:
                logger.error(f"   ❌ URL extraction failed: {result_data.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"   ❌ URL extraction error: {e}")
            return False
    
    async def _generate_article_schema(self, source: NewsSource) -> bool:
        """Generate and validate article schema using real sample URLs"""
        try:
            if not source.sample_urls or len(source.sample_urls) < 2:
                logger.error("   ❌ Need at least 2 sample URLs for article schema generation")
                return False
            
            result = await generate_validated_article_schema(source.url, source.sample_urls)
            result_data = json.loads(result)
            
            if result_data.get("status") in ["success", "partial_success"]:
                source.article_schema = result_data.get("schema")
                source.validation_score = result_data.get("validation_score", 0.0)
                
                # Print detailed comparison results for debugging
                comparisons = result_data.get("comparisons", [])
                schema_extractions = result_data.get("schema_extractions", [])
                ground_truth_extractions = result_data.get("ground_truth_extractions", [])
                sample_urls = result_data.get("sample_urls", source.sample_urls)
                
                if comparisons:
                    logger.info(f"   📊 DETAILED COMPARISON RESULTS:")
                    logger.info(f"   {'='*60}")
                    
                    for i, (comparison, schema_data, llm_data, url) in enumerate(zip(comparisons, schema_extractions, ground_truth_extractions, sample_urls), 1):
                        if comparison:
                            logger.info(f"   🔍 URL {i}: {url}")
                            logger.info(f"   📊 Score: {comparison.get('completeness_score', 0):.1f}%")
                            logger.info(f"   📝 Assessment: {comparison.get('overall_assessment', 'N/A')}")
                            
                            # Show what was missing
                            missing = comparison.get('missing_content', [])
                            if missing:
                                logger.info(f"   ❌ Missing: {'; '.join(missing)}")
                            
                            # Show selector feedback
                            feedback = comparison.get('selector_feedback', [])
                            if feedback:
                                logger.info(f"   💡 Suggestions: {'; '.join(feedback)}")
                            
                            # Show actual extracted content comparison
                            logger.info(f"   📄 CONTENT COMPARISON:")
                            
                            # Schema extraction
                            if schema_data:
                                schema_title = schema_data.get('title', 'MISSING')[:100]
                                schema_content = schema_data.get('content', [])
                                schema_author = schema_data.get('author', 'MISSING')
                                schema_date = schema_data.get('date_published', 'MISSING')
                                
                                if isinstance(schema_content, list):
                                    content_preview = ' '.join([str(item) for item in schema_content[:3]])[:150]
                                else:
                                    content_preview = str(schema_content)[:150]
                                
                                logger.info(f"   🔧 SCHEMA EXTRACTED:")
                                logger.info(f"      Title: {schema_title}...")
                                logger.info(f"      Author: {schema_author}")
                                logger.info(f"      Date: {schema_date}")
                                logger.info(f"      Content: {content_preview}...")
                            
                            # LLM ground truth
                            if llm_data:
                                llm_title = llm_data.get('title', 'MISSING')[:100]
                                llm_content = llm_data.get('content', [])
                                llm_author = llm_data.get('author', 'MISSING')
                                llm_date = llm_data.get('date_published', 'MISSING')
                                
                                if isinstance(llm_content, list):
                                    content_preview = ' '.join([str(item) for item in llm_content[:3]])[:150]
                                else:
                                    content_preview = str(llm_content)[:150]
                                
                                logger.info(f"   🤖 LLM GROUND TRUTH:")
                                logger.info(f"      Title: {llm_title}...")
                                logger.info(f"      Author: {llm_author}")
                                logger.info(f"      Date: {llm_date}")
                                logger.info(f"      Content: {content_preview}...")
                            
                            logger.info(f"   {'-'*40}")
                
                logger.info(f"   ✅ Article schema generated (Score: {source.validation_score:.1f}%)")
                
                # Step 2d: Save to Supabase if validation score is good enough
                min_score_for_save = 90.0  # Only save high-quality sources
                if source.validation_score >= min_score_for_save:
                    logger.info(f"💾 Step 2d: Saving source to Supabase (score {source.validation_score:.1f}% >= {min_score_for_save}%)")
                    
                    # Transform NewsSource data to the format expected by supabase_writer
                    source_data = {
                        "source": {
                            "name": source.name,
                            "url": source.url,
                            "description": f"News source discovered for validation score {source.validation_score:.1f}%"
                        },
                        "link_schema": source.link_schema,
                        "article_schema": source.article_schema,
                        "article_schema_score": source.validation_score,
                        "sample_urls": source.sample_urls
                    }
                    
                    # Call the Supabase writer
                    try:
                        write_result = await write_crawl_source(source_data)
                        write_data = json.loads(write_result)
                        
                        if write_data.get("status") == "success":
                            operation = write_data.get("operation", "unknown")
                            logger.info(f"   ✅ Source saved to database ({operation})")
                        elif write_data.get("status") == "skipped":
                            reason = write_data.get("reason", "unknown")
                            logger.info(f"   ⚠️ Source not saved: {reason}")
                        else:
                            error = write_data.get("error", "unknown error")
                            logger.warning(f"   ❌ Failed to save to database: {error}")
                    except Exception as e:
                        logger.warning(f"   ❌ Database save error: {e}")
                else:
                    logger.info(f"⏭️ Step 2d: Skipping Supabase save (score {source.validation_score:.1f}% < {min_score_for_save}%)")
                
                return True
            else:
                logger.error(f"   ❌ Article schema generation failed: {result_data.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Article schema error: {e}")
            return False
    
    def _source_to_dict(self, source: NewsSource) -> Dict[str, Any]:
        """Convert NewsSource to dictionary for output"""
        return {
            "name": source.name,
            "url": source.url,
            "status": source.status,
            "link_schema": source.link_schema,
            "sample_urls": source.sample_urls,
            "article_schema": source.article_schema,
            "validation_score": source.validation_score
        }
    
    def _generate_summary(self, sources: List[NewsSource]) -> str:
        """Generate a human-readable summary of the processing results"""
        completed = [s for s in sources if s.status == "completed"]
        failed = [s for s in sources if s.status == "failed"]
        
        summary_lines = [
            f"�� Processing Summary (Success = Validation Score ≥80%):",
            f"   ✅ Successfully processed: {len(completed)} sources",
            f"   ❌ Failed: {len(failed)} sources",
            ""
        ]
        
        if completed:
            summary_lines.append("🎉 Successfully Processed Sources (≥80% validation):")
            for source in completed:
                summary_lines.append(f"   • {source.name} (Score: {source.validation_score:.1f}%)")
                summary_lines.append(f"     - Link Schema: {source.link_schema.get('baseSelector', 'N/A') if source.link_schema else 'N/A'}")
                summary_lines.append(f"     - Sample URLs: {len(source.sample_urls) if source.sample_urls else 0}")
                summary_lines.append("")
        
        if failed:
            summary_lines.append("❌ Failed Sources (<80% validation or processing error):")
            for source in failed:
                score_info = f" (Score: {source.validation_score:.1f}%)" if source.validation_score is not None else " (Processing failed)"
                summary_lines.append(f"   • {source.name}{score_info}")
                summary_lines.append(f"     URL: {source.url}")
                if source.validation_score is not None and source.validation_score > 0:
                    summary_lines.append(f"     Issue: Validation score too low ({source.validation_score:.1f}% < 60%)")
                else:
                    summary_lines.append(f"     Issue: Schema generation or extraction failed")
                summary_lines.append("")
        
        return "\n".join(summary_lines)

# Convenience function
async def run_structured_agent(query: str) -> Dict[str, Any]:
    """Run the structured agent with a query"""
    agent = StructuredScroopyAgent()
    return await agent.process_query(query) 