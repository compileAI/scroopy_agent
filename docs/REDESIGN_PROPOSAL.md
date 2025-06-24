# Scroopy Redesign Proposal: Robust Validation System

## Current Problems
1. **Ground Truth Extraction Failure**: LLM extraction fails on same content schema generation targets
2. **Brittle Schema Generation**: Over-specific selectors that break easily  
3. **Backward Validation**: Validating against failed extraction instead of guiding schema creation
4. **No Progressive Improvement**: System doesn't learn from failures or adapt

## Proposed Solution: Multi-Stage Adaptive Validation

### Stage 1: Pre-Validation Schema Generation
Instead of generating one schema and then validating it, generate MULTIPLE schema candidates and test them immediately:

```python
async def generate_robust_article_schema(url: str, sample_urls: List[str]):
    """Generate multiple schema candidates and pick the most robust one"""
    
    # Generate 3 different schema approaches
    candidates = [
        await generate_semantic_schema(url),      # <article>, <main> approach
        await generate_class_based_schema(url),   # Common class patterns
        await generate_fallback_schema(url)       # Generic but reliable selectors
    ]
    
    # Test each candidate against ALL sample URLs immediately
    best_candidate = None
    best_score = 0
    
    for candidate in candidates:
        success_rate = await test_schema_robustness(candidate, sample_urls)
        if success_rate > best_score:
            best_candidate = candidate
            best_score = success_rate
    
    return best_candidate, best_score
```

### Stage 2: Iterative Schema Refinement
When a schema fails, use the failure feedback to improve it:

```python
async def refine_schema_with_feedback(schema: Dict, failed_url: str, failure_reason: str):
    """Use specific failure information to improve the schema"""
    
    if "title not found" in failure_reason:
        # Add more title selector fallbacks
        schema = add_title_fallbacks(schema, failed_url)
    
    if "author not found" in failure_reason:
        # Add more author selector patterns
        schema = add_author_fallbacks(schema, failed_url)
    
    return schema
```

### Stage 3: Success-Based Validation
Instead of LLM ground truth, use successful extractions as the baseline:

```python
async def validate_with_successful_extractions(schema: Dict, sample_urls: List[str]):
    """Validate based on actual extraction success, not LLM comparison"""
    
    results = []
    for url in sample_urls:
        extraction = await extract_with_schema(url, schema)
        
        # Simple, objective validation criteria
        score = calculate_extraction_quality(extraction)
        results.append(score)
    
    return sum(results) / len(results)

def calculate_extraction_quality(extraction: Dict) -> float:
    """Objective quality scoring based on actual content"""
    score = 0
    
    # Title scoring (40% weight)
    title = extraction.get('title', '').strip()
    if title and len(title) > 10 and title not in ['Home', 'News', 'Article']:
        score += 40
    
    # Content scoring (40% weight)  
    content = get_content_text(extraction.get('content', []))
    if len(content) > 200:
        score += 40
    
    # Date scoring (10% weight)
    if extraction.get('date_published'):
        score += 10
        
    # Author scoring (10% weight)
    if extraction.get('author'):
        score += 10
    
    return score
```

### Stage 4: Adaptive Schema Patterns
Build a library of proven selector patterns that work across sites:

```python
ROBUST_SELECTOR_PATTERNS = {
    'title': [
        'h1',                                    # Most common
        'h1[class*="title"]',                   # Title-related classes
        'h1[class*="headline"]',                # Headline classes
        '[data-testid="headline"]',             # Test IDs
        'title',                                # Page title fallback
        '[property="og:title"]'                 # Meta fallback
    ],
    'content': [
        'article p',                            # Semantic HTML
        '[class*="article-body"] p',           # Common patterns
        '[class*="story-content"] p',          # Story patterns
        'main p',                              # Main content
        '.content p, .post-content p'          # Generic fallbacks
    ],
    'author': [
        '[class*="author"]',                   # Author classes
        '[class*="byline"]',                   # Byline patterns
        '[rel="author"]',                      # Semantic markup
        'address',                             # Author address
        '[data-testid="author"]'               # Test IDs
    ]
}
```

## Implementation Plan

### Phase 1: Replace Ground Truth Validation (Week 1)
- Remove LLM ground truth extraction entirely
- Implement objective quality scoring
- Test on current failing cases

### Phase 2: Multi-Candidate Schema Generation (Week 2)  
- Generate multiple schema approaches per site
- Test all candidates immediately
- Pick most robust option

### Phase 3: Iterative Improvement (Week 3)
- Add failure feedback loops
- Build adaptive schema refinement
- Create pattern library from successful extractions

### Phase 4: Progressive Learning (Week 4)
- Save successful patterns to database
- Use historical data to improve future schema generation
- Build confidence scores for different selector types

## Expected Benefits

1. **Higher Success Rate**: Multiple candidates + immediate testing = better schemas
2. **More Robust Selectors**: Fallback patterns prevent single points of failure
3. **Faster Iteration**: No waiting for LLM ground truth that often fails
4. **Progressive Improvement**: System learns from both successes and failures
5. **Objective Validation**: Clear, measurable quality criteria

## Migration Strategy

We can implement this gradually:
1. Keep current system but add objective validation alongside LLM validation
2. Compare results and tune objective validation criteria
3. Gradually phase out LLM ground truth as objective validation proves reliable
4. Add multi-candidate generation and iterative improvement

This approach focuses on **what actually works** rather than trying to validate against potentially flawed ground truth. 