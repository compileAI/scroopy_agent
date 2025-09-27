import json
import time
import html
from typing import List, Dict, Any, Optional
from datetime import datetime

from bs4 import BeautifulSoup

# Import from the new utils structure
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from utils.http import create_session
from utils.settings import HF_PAPERS_URL, HF_PAPERS_SOURCE_ID


def fetch_daily_papers_html(url: str = HF_PAPERS_URL) -> str:
    """Fetch the HuggingFace papers page HTML."""
    print(f"🔍 Fetching page: {url}")
    session = create_session()
    response = session.get(url)
    response.raise_for_status()
    print(f"✅ Got HTML ({len(response.text)} bytes)")
    return response.text


def extract_props_json(html_text: str) -> Dict[str, Any]:
    """Extract the DailyPapers JSON data from the page props."""
    print("🔎 Parsing for DailyPapers data-props…")
    soup = BeautifulSoup(html_text, "html.parser")

    # Prefer targeting by data-target attribute
    hydrater = soup.select_one('[data-target="DailyPapers"]')
    if hydrater is None:
        # Fallback: look for svelte hydrater nodes that carry data-props
        for node in soup.find_all(attrs={"data-props": True}):
            if "dailyPapers" in node.get("data-props", ""):
                hydrater = node
                break

    if hydrater is None:
        raise RuntimeError("Could not find DailyPapers hydrater in page")

    raw_props = hydrater.get("data-props", "")
    if not raw_props:
        raise RuntimeError("Found DailyPapers hydrater but it has empty data-props")

    # data-props may be HTML-escaped. Unescape then parse.
    unescaped = html.unescape(raw_props)
    try:
        props = json.loads(unescaped)
        print("✅ Parsed data-props JSON")
        return props
    except json.JSONDecodeError:
        # Last-ditch: remove stray newlines/whitespace and try again
        compact = unescaped.replace("\n", " ").replace("\r", " ")
        props = json.loads(compact)
        print("✅ Parsed data-props JSON (after compaction)")
        return props


def normalize_daily_papers(props: Dict[str, Any]) -> List[SourceArticle]:
    """Convert the raw dailyPapers data to SourceArticle objects."""
    papers_raw = props.get("dailyPapers") or []
    print(f"🧮 Found {len(papers_raw)} items in dailyPapers")

    results: List[SourceArticle] = []
    for idx, item in enumerate(papers_raw, start=1):
        paper_meta = item.get("paper") or {}
        arxiv_id = str(paper_meta.get("id", "")).strip()
        title = (item.get("title") or paper_meta.get("title") or "").strip()
        summary = (item.get("summary") or paper_meta.get("summary") or "").strip()

        authors_list = item.get("authors") or paper_meta.get("authors") or []
        author_names = [a.get("name", "").strip() for a in authors_list if a and a.get("name")]
        authors = ", ".join([n for n in author_names if n])

        # arXiv original publish date (for content prefix)
        published_at = (item.get("publishedAt") or paper_meta.get("publishedAt") or "").strip()
        arxiv_published_date = published_at
        try:
            if published_at:
                dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                arxiv_published_date = dt.date().isoformat()
        except Exception:
            pass

        # submitted date used as the published date in our schema
        submitted_on_daily_at = (
            paper_meta.get("submittedOnDailyAt")
            or item.get("submittedOnDailyAt")
            or ""
        )
        submitted_date = submitted_on_daily_at
        try:
            if submitted_on_daily_at:
                sdt = datetime.fromisoformat(submitted_on_daily_at.replace("Z", "+00:00"))
                submitted_date = sdt.date().isoformat()
        except Exception:
            pass

        link = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else HF_PAPERS_URL

        # Compose content with arXiv date prefix
        content = f"(Originally posted to arXiv on: {arxiv_published_date})\n\n{summary}".strip()

        # Deterministic id for safe upserts
        safe_arxiv = arxiv_id.replace("/", "-") if arxiv_id else "no-arxiv-id"
        deterministic_id = f"hf-papers-{safe_arxiv}-{submitted_date}"

        source_article = SourceArticle(
            published=submitted_date,
            title=title,
            content=content,
            author=authors,
            source_id=HF_PAPERS_SOURCE_ID,
            url=link
        )
        # Override the auto-generated ID with the deterministic one
        source_article.id = deterministic_id
        results.append(source_article)

        if idx <= 3:  # brief progressive output for first few
            print(f"  • [{idx}] {title[:80]}…  (submitted: {submitted_date})")

    return results


def run(limit: Optional[int] = None) -> List[SourceArticle]:
    """Main entry point for HF Daily Papers scraper.
    
    Args:
        limit: Optional limit on number of papers to return
        
    Returns:
        List of SourceArticle objects
    """
    start = time.time()
    html_text = fetch_daily_papers_html()
    props = extract_props_json(html_text)
    papers = normalize_daily_papers(props)
    
    if limit:
        papers = papers[:limit]
        print(f"✂️ Limiting to {limit} results")
    
    elapsed = time.time() - start
    print(f"⏱️ HF Daily Papers scrape completed in {elapsed:.2f}s")
    return papers


if __name__ == "__main__":
    # For testing the scraper directly
    import argparse
    from dataclasses import asdict

    parser = argparse.ArgumentParser(description="Scrape Hugging Face Daily Papers")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of papers")
    parser.add_argument("--save-json", type=str, help="Save results to JSON file")
    args = parser.parse_args()

    print("🤗 Testing HF Daily Papers scraper")
    papers = run(limit=args.limit)

    print(f"\n📋 Found {len(papers)} papers:")
    for i, p in enumerate(papers[:3], start=1):
        print(f"\n{i}. {p.title}")
        print(f"   👥 {p.author}")
        print(f"   📅 {p.published}")
        print(f"   🔗 {p.url}")

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in papers], f, ensure_ascii=False, indent=2)
        print(f"💾 Saved to {args.save_json}")