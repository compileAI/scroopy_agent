"""
LangGraph-based Scroopy Agent with improved state management and validation feedback
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, TypedDict, Annotated
from dataclasses import dataclass, asdict

from langgraph.graph import StateGraph, END

# Import existing tools
from tools.discovery import discover_sources
from tools.link_schema_generator import generate_link_schema
from tools.url_extractor import extract_urls_with_schema
from tools.article_schema_generator_enhanced import generate_validated_article_schema_with_feedback
from tools.supabase_writer import write_crawl_source

logger = logging.getLogger(__name__)

# State definition for LangGraph
class AgentState(TypedDict):
    """State tracked throughout the workflow"""
    query: str
    sources: List[Dict[str, Any]]
    current_source_index: int
    current_source: Optional[Dict[str, Any]]
    workflow_status: str  # discovering, processing, completed, failed
    errors: List[str]
    retry_count: int
    validation_feedback: List[str]
    final_results: Dict[str, Any]
    ground_truth_cache: Dict[str, Any]  # Cache for LLM extractions across all sources

class NewsSourceProcessor:
    """LangGraph-based news source processing workflow"""
    
    def __init__(self):
        self.graph = self._create_workflow()
        
    def _create_workflow(self) -> StateGraph:
        """Create the LangGraph workflow"""
        
        # Create the state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes for each step
        workflow.add_node("discover_sources", self._discover_sources_node)
        workflow.add_node("process_source", self._process_source_node)
        workflow.add_node("generate_link_schema", self._generate_link_schema_node)
        workflow.add_node("extract_sample_urls", self._extract_sample_urls_node)
        workflow.add_node("generate_article_schema", self._generate_article_schema_node)
        workflow.add_node("validate_and_improve", self._validate_and_improve_node)
        workflow.add_node("save_source", self._save_source_node)
        workflow.add_node("next_source", self._next_source_node)
        workflow.add_node("finalize_results", self._finalize_results_node)
        
        # Add edges
        workflow.set_entry_point("discover_sources")
        workflow.add_edge("discover_sources", "process_source")
        workflow.add_edge("process_source", "generate_link_schema")
        workflow.add_edge("generate_link_schema", "extract_sample_urls")
        workflow.add_edge("extract_sample_urls", "generate_article_schema")
        workflow.add_edge("generate_article_schema", "validate_and_improve")
        
        # Conditional edges for validation feedback loop
        workflow.add_conditional_edges(
            "validate_and_improve",
            self._should_retry_validation,
            {
                "retry": "generate_article_schema",  # Retry with feedback
                "save": "save_source",              # Good enough to save
                "skip": "next_source",              # Skip this source
            }
        )
        
        workflow.add_edge("save_source", "next_source")
        
        # Conditional edges for processing next source
        workflow.add_conditional_edges(
            "next_source",
            self._should_process_next_source,
            {
                "continue": "process_source",    # More sources to process
                "finish": "finalize_results",    # All sources done
            }
        )
        
        workflow.add_edge("finalize_results", END)
        
        return workflow.compile()
    
    async def _discover_sources_node(self, state: AgentState) -> AgentState:
        """Node: Discover news sources for the query"""
        logger.info(f"🔍 Discovering sources for: {state['query']}")
        
        try:
            result = await discover_sources(state["query"])
            result_data = json.loads(result)
            
            if result_data.get("status") == "success":
                sources = []
                for source_data in result_data.get("sources", []):
                    source = {
                        "name": source_data.get("name", "Unknown"),
                        "url": source_data.get("url", ""),
                        "status": "pending",
                        "link_schema": None,
                        "sample_urls": None,
                        "article_schema": None,
                        "validation_score": None,
                        "validation_attempts": 0,
                        "validation_feedback": []
                    }
                    sources.append(source)
                    
                state["sources"] = sources
                state["current_source_index"] = 0
                state["workflow_status"] = "processing"
                logger.info(f"✅ Discovered {len(sources)} sources")
                
            else:
                error_msg = f"Source discovery failed: {result_data.get('error', 'Unknown')}"
                state["errors"].append(error_msg)
                state["workflow_status"] = "failed"
                logger.error(f"❌ {error_msg}")
                
        except Exception as e:
            error_msg = f"Discovery error: {str(e)}"
            state["errors"].append(error_msg)
            state["workflow_status"] = "failed"
            logger.error(f"❌ {error_msg}")
            
        return state
    
    async def _process_source_node(self, state: AgentState) -> AgentState:
        """Node: Set up processing for current source"""
        if state["current_source_index"] < len(state["sources"]):
            current_source = state["sources"][state["current_source_index"]]
            state["current_source"] = current_source
            current_source["status"] = "processing"
            
            logger.info(f"🏭 Processing source {state['current_source_index'] + 1}/{len(state['sources'])}: {current_source['name']}")
        
        return state
    
    async def _generate_link_schema_node(self, state: AgentState) -> AgentState:
        """Node: Generate link extraction schema"""
        current_source = state["current_source"]
        
        try:
            logger.info(f"🔗 Generating link schema for {current_source['name']}")
            result = await generate_link_schema(current_source["url"])
            result_data = json.loads(result)
            
            if result_data.get("status") == "success":
                current_source["link_schema"] = result_data.get("schema")
                logger.info(f"✅ Link schema generated")
            else:
                error_msg = f"Link schema generation failed: {result_data.get('error', 'Unknown')}"
                current_source["errors"] = current_source.get("errors", []) + [error_msg]
                current_source["status"] = "failed"
                logger.error(f"❌ {error_msg}")
                
        except Exception as e:
            error_msg = f"Link schema error: {str(e)}"
            current_source["errors"] = current_source.get("errors", []) + [error_msg]
            current_source["status"] = "failed"
            logger.error(f"❌ {error_msg}")
            
        return state
    
    async def _extract_sample_urls_node(self, state: AgentState) -> AgentState:
        """Node: Extract sample URLs using link schema"""
        current_source = state["current_source"]
        
        if current_source["status"] == "failed" or not current_source.get("link_schema"):
            return state
            
        try:
            logger.info(f"🎯 Extracting sample URLs for {current_source['name']}")
            result = await extract_urls_with_schema(
                current_source["url"],
                json.dumps(current_source["link_schema"]),
                max_urls=5
            )
            result_data = json.loads(result)
            
            if result_data.get("status") == "success":
                urls = result_data.get("urls", [])
                if len(urls) >= 2:
                    current_source["sample_urls"] = urls
                    logger.info(f"✅ Extracted {len(urls)} sample URLs")
                else:
                    error_msg = f"Only extracted {len(urls)} URLs, need at least 2"
                    current_source["errors"] = current_source.get("errors", []) + [error_msg]
                    current_source["status"] = "failed"
                    logger.warning(f"⚠️ {error_msg}")
            else:
                error_msg = f"URL extraction failed: {result_data.get('error', 'Unknown')}"
                current_source["errors"] = current_source.get("errors", []) + [error_msg]
                current_source["status"] = "failed"
                logger.error(f"❌ {error_msg}")
                
        except Exception as e:
            error_msg = f"URL extraction error: {str(e)}"
            current_source["errors"] = current_source.get("errors", []) + [error_msg]
            current_source["status"] = "failed"
            logger.error(f"❌ {error_msg}")
            
        return state
    
    async def _generate_article_schema_node(self, state: AgentState) -> AgentState:
        """Node: Generate and validate article schema"""
        current_source = state["current_source"]
        
        if current_source["status"] == "failed" or not current_source.get("sample_urls"):
            logger.info(f"⏭️ Skipping article schema generation - source failed or no sample URLs")
            return state
        
        # Safety check for max attempts
        max_attempts = 3
        if current_source.get("validation_attempts", 0) >= max_attempts:
            logger.warning(f"⚠️ Skipping article schema generation - max attempts ({max_attempts}) already reached")
            current_source["status"] = "failed"
            return state
            
        try:
            logger.info(f"📰 Generating article schema for {current_source['name']} (attempt {current_source['validation_attempts'] + 1})")
            
            # Use enhanced schema generator with validation feedback and shared cache
            previous_schema = current_source.get("article_schema")  # Get schema from previous attempt
            result = await generate_validated_article_schema_with_feedback(
                current_source["url"], 
                current_source["sample_urls"],
                current_source["validation_feedback"] if current_source["validation_feedback"] else None,
                state["ground_truth_cache"],  # Pass shared cache
                previous_schema  # Pass previous schema for context
            )
            result_data = json.loads(result)
            
            if result_data.get("status") in ["success", "partial_success"]:
                current_source["article_schema"] = result_data.get("schema")
                current_source["validation_score"] = result_data.get("validation_score", 0.0)
                current_source["validation_attempts"] += 1
                
                # Store detailed validation results for feedback
                current_source["validation_details"] = {
                    "comparisons": result_data.get("comparisons", []),
                    "schema_extractions": result_data.get("schema_extractions", []),
                    "ground_truth_extractions": result_data.get("ground_truth_extractions", [])
                }
                
                logger.info(f"✅ Article schema generated (Score: {current_source['validation_score']:.1f}%)")
            else:
                error_msg = f"Article schema generation failed: {result_data.get('error', 'Unknown')}"
                current_source["errors"] = current_source.get("errors", []) + [error_msg]
                logger.error(f"❌ {error_msg}")
                
        except Exception as e:
            error_msg = f"Article schema error: {str(e)}"
            current_source["errors"] = current_source.get("errors", []) + [error_msg]
            logger.error(f"❌ {error_msg}")
            
        return state
    
    async def _validate_and_improve_node(self, state: AgentState) -> AgentState:
        """Node: Analyze validation results and generate improvement feedback"""
        current_source = state["current_source"]
        
        if current_source.get("validation_score") is None:
            current_source["status"] = "failed"
            current_source["decision"] = "skip"
            logger.error(f"❌ No validation score available - skipping source")
            return state
            
        validation_score = current_source["validation_score"]
        max_attempts = 3  # Total attempts at LangGraph level
        min_score_threshold = 80.0
        current_attempts = current_source.get("validation_attempts", 0)
        
        logger.info(f"📊 Validation analysis: Score={validation_score:.1f}%, Attempt={current_attempts}/{max_attempts}")
        
        # Determine next action based on score and attempts
        if validation_score >= min_score_threshold:
            # Good enough to save
            current_source["status"] = "completed"
            current_source["decision"] = "save"
            logger.info(f"✅ Validation passed (Score: {validation_score:.1f}%) - ready to save")
            
        elif current_attempts >= max_attempts:
            # Max attempts reached - accept best effort or skip
            if validation_score >= 50.0:  # Accept if at least 50%
                current_source["status"] = "completed"
                current_source["decision"] = "save"
                logger.warning(f"⚠️ Max attempts reached but score acceptable ({validation_score:.1f}%) - saving")
            else:
                current_source["status"] = "failed" 
                current_source["decision"] = "skip"
                logger.warning(f"❌ Max attempts reached and score too low ({validation_score:.1f}%) - skipping source")
            
        else:
            # Generate feedback for improvement
            current_source["decision"] = "retry"
            feedback = self._generate_validation_feedback(current_source)
            current_source["validation_feedback"].append(feedback)
            logger.info(f"🔄 Validation needs improvement (Score: {validation_score:.1f}%) - retrying with feedback")
            logger.info(f"💡 Feedback: {feedback}")
            
        return state
    
    def _generate_validation_feedback(self, source: Dict[str, Any]) -> str:
        """Generate specific feedback based on validation results"""
        feedback_items = []
        
        # Analyze validation details if available
        validation_details = source.get("validation_details", {})
        comparisons = validation_details.get("comparisons", [])
        
        if comparisons:
            for comparison in comparisons:
                if comparison:
                    # Look for missing content patterns and generate SPECIFIC selector suggestions
                    missing_content = comparison.get("missing_content", [])
                    if missing_content:
                        for missing in missing_content:
                            if "title" in missing.lower():
                                feedback_items.append("TITLE SELECTOR: Use 'h1.entry-title, h1.post-title, h1[class*=\"title\"]' for title extraction")
                            elif "content" in missing.lower():
                                feedback_items.append("CONTENT SELECTOR: Use '.entry-content p, .post-content p, [class*=\"content\"] p' for content paragraphs")
                            elif "author" in missing.lower():
                                feedback_items.append("AUTHOR SELECTOR: Use '.author, .byline, [rel=\"author\"], .post-author' for author extraction")
                            elif "date" in missing.lower():
                                feedback_items.append("DATE SELECTOR: Use 'time[datetime], .entry-date, .published-date, [class*=\"date\"]' for dates")
                    
                    # Look for selector feedback from LLM
                    selector_feedback = comparison.get("selector_feedback", [])
                    if selector_feedback:
                        feedback_items.extend(selector_feedback)
        
        # Add structural feedback based on score
        score = source["validation_score"]
        if score < 30:
            feedback_items.append("SCHEMA STRUCTURE: Use more specific baseSelector like 'main, article, .main-content, .post' instead of generic elements")
        elif score < 70:
            feedback_items.append("SELECTOR SPECIFICITY: Add class-based selectors like '.entry-title' instead of generic 'h1'")
            
        return feedback_items[0] if feedback_items else "GENERAL: Review CSS selectors for better specificity"
    
    def _should_retry_validation(self, state: AgentState) -> str:
        """Conditional edge: Determine if we should retry validation"""
        current_source = state["current_source"]
        decision = current_source.get("decision", "skip")
        
        # Add extra safety check to prevent infinite loops
        attempts = current_source.get("validation_attempts", 0)
        max_attempts = 3
        
        logger.info(f"🔀 Validation routing decision: '{decision}' (attempts: {attempts}/{max_attempts})")
        
        if decision == "save":
            return "save"
        elif decision == "retry" and attempts < max_attempts:
            return "retry"
        else:
            # Force skip if decision is unclear or max attempts exceeded
            if decision == "retry" and attempts >= max_attempts:
                logger.warning(f"⚠️ Forcing skip - retry requested but max attempts exceeded ({attempts}/{max_attempts})")
            return "skip"
    
    async def _save_source_node(self, state: AgentState) -> AgentState:
        """Node: Save validated source to database"""
        current_source = state["current_source"]
        
        try:
            logger.info(f"💾 Saving {current_source['name']} to database")
            
            source_data = {
                "source": {
                    "name": current_source["name"],
                    "url": current_source["url"],
                    "description": f"News source with validation score {current_source['validation_score']:.1f}%"
                },
                "link_schema": current_source["link_schema"],
                "article_schema": current_source["article_schema"],
                "article_schema_score": current_source["validation_score"],
                "sample_urls": current_source["sample_urls"]
            }
            
            write_result = await write_crawl_source(source_data)
            write_data = json.loads(write_result)
            
            if write_data.get("status") == "success":
                operation = write_data.get("operation", "unknown")
                logger.info(f"✅ Source saved to database ({operation})")
                current_source["saved"] = True
            else:
                error = write_data.get("error", "unknown error")
                logger.warning(f"❌ Failed to save to database: {error}")
                current_source["saved"] = False
                
        except Exception as e:
            error_msg = f"Database save error: {str(e)}"
            logger.warning(f"❌ {error_msg}")
            current_source["saved"] = False
            
        return state
    
    async def _next_source_node(self, state: AgentState) -> AgentState:
        """Node: Move to next source or finish"""
        state["current_source_index"] += 1
        logger.info(f"➡️ Moving to next source ({state['current_source_index']}/{len(state['sources'])})")
        return state
    
    def _should_process_next_source(self, state: AgentState) -> str:
        """Conditional edge: Check if there are more sources to process"""
        if state["current_source_index"] < len(state["sources"]):
            return "continue"
        else:
            return "finish"
    
    async def _finalize_results_node(self, state: AgentState) -> AgentState:
        """Node: Generate final results summary"""
        sources = state["sources"]
        completed_sources = [s for s in sources if s["status"] == "completed"]
        failed_sources = [s for s in sources if s["status"] == "failed"]
        
        logger.info(f"🏁 Workflow completed: {len(completed_sources)} successful, {len(failed_sources)} failed")
        
        state["final_results"] = {
            "status": "success",
            "query": state["query"],
            "sources_processed": len(sources),
            "sources_completed": len(completed_sources),
            "sources_failed": len(failed_sources),
            "sources": sources,
            "summary": self._generate_summary(sources)
        }
        
        state["workflow_status"] = "completed"
        return state
    
    def _generate_summary(self, sources: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary"""
        completed = [s for s in sources if s["status"] == "completed"]
        failed = [s for s in sources if s["status"] == "failed"]
        
        summary_lines = [
            f"🎯 Processing Summary:",
            f"   ✅ {len(completed)} sources completed and saved",
            f"   ❌ {len(failed)} sources failed",
        ]
        
        if completed:
            summary_lines.append("   📊 Successful sources:")
            for source in completed:
                score = source.get("validation_score", 0)
                attempts = source.get("validation_attempts", 1)
                summary_lines.append(f"      • {source['name']}: {score:.1f}% (after {attempts} attempts)")
        
        return "\n".join(summary_lines)
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """Main entry point for processing a query"""
        logger.info(f"🤖 Starting LangGraph agent for query: {query}")
        
        # Initialize state
        initial_state: AgentState = {
            "query": query,
            "sources": [],
            "current_source_index": 0,
            "current_source": None,
            "workflow_status": "discovering",
            "errors": [],
            "retry_count": 0,
            "validation_feedback": [],
            "final_results": {},
            "ground_truth_cache": {}  # Persistent cache across all sources and attempts
        }
        
        # Run the workflow
        try:
            final_state = await self.graph.ainvoke(
                initial_state, 
                config={"recursion_limit": 50}
            )
            return final_state["final_results"]
            
        except Exception as e:
            logger.error(f"❌ Workflow error: {e}")
            return {
                "status": "error",
                "message": f"Workflow failed: {str(e)}",
                "sources": []
            }

# Convenience function to match existing interface
async def run_langgraph_agent(query: str) -> Dict[str, Any]:
    """Run the LangGraph-based agent"""
    processor = NewsSourceProcessor()
    return await processor.process_query(query)