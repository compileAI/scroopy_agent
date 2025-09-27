"""
Reddit scraper
Fetches posts from Reddit subreddits and converts them to SourceArticle objects.
"""
import os
import logging
from datetime import datetime, timezone
from typing import List
from dotenv import load_dotenv

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.news_sources import RedditSource

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_ACCOUNT_USERNAME = os.getenv("REDDIT_ACCOUNT_USERNAME")
REDDIT_ACCOUNT_PASSWORD = os.getenv("REDDIT_ACCOUNT_PASSWORD")


async def query_subreddit_async(reddit_sources: List[RedditSource]) -> List[SourceArticle]:
    """
    Query Reddit subreddits asynchronously and convert posts to SourceArticle objects.
    
    Args:
        reddit_sources: List of RedditSource objects to scrape
        
    Returns:
        List of SourceArticle objects
    """
    try:
        import asyncpraw
        from asyncpraw.models import MoreComments
    except ImportError:
        logger.error("asyncpraw not installed - Reddit scraping unavailable")
        return []
    
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_ACCOUNT_USERNAME, REDDIT_ACCOUNT_PASSWORD]):
        logger.error("Reddit API credentials not configured")
        return []
    
    articles = []
    
    async with asyncpraw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent="scroopy-agent-scraper",
        username=REDDIT_ACCOUNT_USERNAME,
        password=REDDIT_ACCOUNT_PASSWORD
    ) as reddit_async:
        
        for reddit_source in reddit_sources:
            logger.info(f"📱 Scraping Reddit: r/{reddit_source.subreddit}")
            
            try:
                subreddit = await reddit_async.subreddit(reddit_source.subreddit, fetch=True)
                submission_list = []
                
                async for submission in subreddit.top(time_filter='day', limit=50):
                    # Filter by flair if specified
                    if reddit_source.flairs and submission.link_flair_text not in reddit_source.flairs:
                        continue
                    
                    submission_list.append((submission, reddit_source))
                
                # Sort by score
                submission_list = sorted(submission_list, key=lambda x: x[0].score, reverse=True)
                
                logger.info(f"Found {len(submission_list)} posts from r/{reddit_source.subreddit}")
                
                # Convert to SourceArticle objects
                for post, source in submission_list:
                    try:
                        # Build content with comments
                        content = f"POST ({post.score} upvotes):\n{post.selftext}\n\nCOMMENTS:\n"
                        
                        # Get top comments
                        try:
                            comments = [
                                c for c in await post.comments() 
                                if not isinstance(c, asyncpraw.models.MoreComments)
                            ]
                            
                            # Sort by score and take top 3
                            top_comments = sorted(comments, key=lambda x: x.score, reverse=True)[:3]
                            
                            if top_comments:
                                for i, comment in enumerate(top_comments, start=1):
                                    content += f"- Comment {i} ({comment.score} upvotes): {comment.body}\n"
                                    
                                    # Get top 2 replies for each comment
                                    try:
                                        replies = [
                                            reply for reply in (await comment.refresh()).replies
                                            if not isinstance(reply, asyncpraw.models.MoreComments)
                                        ]
                                        
                                        top_replies = sorted(replies, key=lambda x: x.score, reverse=True)[:2]
                                        
                                        for j, reply in enumerate(top_replies, start=1):
                                            content += f"    - Reply {i}.{j}: {reply.body}\n"
                                    except Exception as e:
                                        logger.debug(f"Error getting replies for comment: {e}")
                            else:
                                content += "No comments available."
                        except Exception as e:
                            logger.debug(f"Error getting comments for post: {e}")
                            content += "Comments unavailable."
                        
                        # Create SourceArticle
                        article = SourceArticle(
                            published=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                            title=post.title,
                            content=content,
                            author=str(post.author) if post.author else "Unknown",
                            source_id=source.source_id,
                            url=post.url
                        )
                        
                        articles.append(article)
                        
                    except Exception as e:
                        logger.error(f"Error processing Reddit post: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error scraping r/{reddit_source.subreddit}: {e}")
                continue
    
    logger.info(f"📱 Reddit scraping complete: {len(articles)} articles collected")
    return articles


def query_subreddit_sync(reddit_sources: List[RedditSource]) -> List[SourceArticle]:
    """
    Synchronous version of Reddit scraping (fallback).
    
    Args:
        reddit_sources: List of RedditSource objects to scrape
        
    Returns:
        List of SourceArticle objects
    """
    try:
        import praw
        from praw.models import MoreComments
    except ImportError:
        logger.error("praw not installed - Reddit scraping unavailable")
        return []
    
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_ACCOUNT_USERNAME, REDDIT_ACCOUNT_PASSWORD]):
        logger.error("Reddit API credentials not configured")
        return []
    
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent="scroopy-agent-scraper",
        username=REDDIT_ACCOUNT_USERNAME,
        password=REDDIT_ACCOUNT_PASSWORD
    )
    
    articles = []
    
    for reddit_source in reddit_sources:
        logger.info(f"📱 Scraping Reddit: r/{reddit_source.subreddit}")
        
        try:
            subreddit = reddit.subreddit(reddit_source.subreddit)
            top_submissions = subreddit.top(time_filter='day', limit=50)
            
            # Filter by flair if specified
            flair_filtered = [
                (post, reddit_source) for post in top_submissions 
                if not reddit_source.flairs or post.link_flair_text in reddit_source.flairs
            ]
            
            # Sort by score
            submission_list = sorted(flair_filtered, key=lambda x: x[0].score, reverse=True)
            
            logger.info(f"Found {len(submission_list)} posts from r/{reddit_source.subreddit}")
            
            # Convert to SourceArticle objects
            for post, source in submission_list:
                try:
                    # Build content with comments
                    content = f"POST ({post.score} upvotes):\n{post.selftext}\n\nCOMMENTS:\n"
                    
                    # Get top comments
                    comments = [
                        c for c in post.comments if not isinstance(c, praw.models.MoreComments)
                    ]
                    
                    # Sort by score and take top 3
                    top_comments = sorted(comments, key=lambda x: x.score, reverse=True)[:3]
                    
                    if top_comments:
                        for i, comment in enumerate(top_comments, start=1):
                            content += f"- Comment {i} ({comment.score} upvotes): {comment.body}\n"
                            
                            # Get top 2 replies for each comment
                            replies = [
                                reply for reply in sorted(comment.replies, key=lambda x: x.score, reverse=True)[:2]
                                if not isinstance(reply, praw.models.MoreComments)
                            ]
                            
                            for j, reply in enumerate(replies, start=1):
                                content += f"    - Reply {i}.{j}: {reply.body}\n"
                    else:
                        content += "No comments available."
                    
                    # Create SourceArticle
                    article = SourceArticle(
                        published=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                        title=post.title,
                        content=content,
                        author=str(post.author) if post.author else "Unknown",
                        source_id=source.source_id,
                        url=post.url
                    )
                    
                    articles.append(article)
                    
                except Exception as e:
                    logger.error(f"Error processing Reddit post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping r/{reddit_source.subreddit}: {e}")
            continue
    
    logger.info(f"📱 Reddit scraping complete: {len(articles)} articles collected")
    return articles


async def run_async(limit: int = None) -> List[SourceArticle]:
    """
    Async main entry point for Reddit scraper.
    
    Args:
        limit: Optional limit on number of articles to return
        
    Returns:
        List of SourceArticle objects
    """
    from utils.supabase import get_active_reddit_sources
    
    logger.info("🚀 Starting Reddit scraper (async)")
    
    # Get active Reddit sources from database
    reddit_sources = get_active_reddit_sources()
    
    if not reddit_sources:
        logger.warning("No active Reddit sources found")
        return []
    
    # Fetch articles from all sources
    articles = await query_subreddit_async(reddit_sources)
    
    # Apply limit if specified
    if limit and len(articles) > limit:
        articles = articles[:limit]
        logger.info(f"✂️ Limited results to {limit} articles")
    
    logger.info(f"✅ Reddit scraper completed: {len(articles)} articles")
    return articles


def run(limit: int = None) -> List[SourceArticle]:
    """
    Sync main entry point for Reddit scraper.
    
    Args:
        limit: Optional limit on number of articles to return
        
    Returns:
        List of SourceArticle objects
    """
    from utils.supabase import get_active_reddit_sources
    
    logger.info("🚀 Starting Reddit scraper (sync)")
    
    # Get active Reddit sources from database
    reddit_sources = get_active_reddit_sources()
    
    if not reddit_sources:
        logger.warning("No active Reddit sources found")
        return []
    
    # Fetch articles from all sources
    articles = query_subreddit_sync(reddit_sources)
    
    # Apply limit if specified
    if limit and len(articles) > limit:
        articles = articles[:limit]
        logger.info(f"✂️ Limited results to {limit} articles")
    
    logger.info(f"✅ Reddit scraper completed: {len(articles)} articles")
    return articles


if __name__ == "__main__":
    # For testing the scraper directly
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Reddit Scraper")
    parser.add_argument("--limit", type=int, help="Limit number of articles")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--sync", action="store_true", help="Use synchronous version")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if args.sync:
        articles = run(limit=args.limit)
    else:
        articles = asyncio.run(run_async(limit=args.limit))
    
    if args.dry_run:
        logger.info(f"🔎 Dry run: would write {len(articles)} articles to database")
    else:
        from utils.supabase import upsert_source_articles
        inserted = upsert_source_articles(articles)
        logger.info(f"💾 Inserted {len(inserted)} new articles to database")
