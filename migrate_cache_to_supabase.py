#!/usr/bin/env python3
"""
Migration script: Transfer cache.json to Supabase stagehand_cache table

Usage:
    python migrate_cache_to_supabase.py

This script:
1. Reads the existing cache/cache.json file
2. Parses each cache entry
3. Determines the cache type and url_hash from the key
4. Bulk inserts all entries into the Supabase stagehand_cache table

Run this ONCE before deploying to Cloud Run.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv

# Add src to path for imports
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.supabase import get_supabase_client

# Load environment variables
load_dotenv()

# Paths
CACHE_FILE = Path(__file__).parent / "cache" / "cache.json"


def parse_cache_key(key: str) -> Tuple[str, str]:
    """
    Parse cache key to determine type and url_hash.
    
    Examples:
        dom_hash_2fba88e65934 -> ("dom_hash", "2fba88e65934")
        last_link_016c3128ff72 -> ("last_link", "016c3128ff72")
        link_extraction_27b9ad2893b9 -> ("link_extraction", "27b9ad2893b9")
        article_extraction_ad294a8770e2 -> ("article_extraction", "ad294a8770e2")
    """
    parts = key.split("_")
    
    if key.startswith("dom_hash_"):
        return ("dom_hash", parts[-1])
    elif key.startswith("last_link_"):
        return ("last_link", parts[-1])
    elif key.startswith("link_extraction_"):
        return ("link_extraction", parts[-1])
    elif key.startswith("article_extraction_"):
        return ("article_extraction", parts[-1])
    else:
        # Unknown type, store as "other"
        return ("other", "")


def load_json_cache() -> Dict[str, Any]:
    """Load the existing cache.json file."""
    if not CACHE_FILE.exists():
        print(f"❌ Cache file not found: {CACHE_FILE}")
        sys.exit(1)
    
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        print(f"✅ Loaded {len(data)} entries from {CACHE_FILE}")
        return data
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing cache.json: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading cache.json: {e}")
        sys.exit(1)


def transform_to_supabase_rows(cache_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform cache.json entries to Supabase row format."""
    rows = []
    
    for key, value in cache_data.items():
        cache_type, url_hash = parse_cache_key(key)
        
        # Convert value to JSONB-compatible format
        # Strings and numbers get wrapped in a simple object
        if isinstance(value, (str, int, float, bool)):
            jsonb_value = {"value": value}
        elif isinstance(value, (dict, list)):
            jsonb_value = value
        elif value is None:
            jsonb_value = {"value": None}
        else:
            # Convert to string for unknown types
            jsonb_value = {"value": str(value)}
        
        row = {
            "key": key,
            "value": jsonb_value,
            "cache_type": cache_type,
            "url_hash": url_hash if url_hash else None
        }
        rows.append(row)
    
    return rows


def migrate_to_supabase(rows: List[Dict[str, Any]], batch_size: int = 100) -> None:
    """Insert cache entries into Supabase in batches."""
    try:
        supabase = get_supabase_client()
    except ValueError as e:
        print(f"❌ Supabase configuration error: {e}")
        print("   Make sure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in .env")
        sys.exit(1)
    
    total_rows = len(rows)
    print(f"\n📤 Migrating {total_rows} cache entries to Supabase...")
    
    # Insert in batches to avoid hitting API limits
    for i in range(0, total_rows, batch_size):
        batch = rows[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_rows + batch_size - 1) // batch_size
        
        try:
            # Use upsert to handle any duplicates
            result = supabase.table('stagehand_cache').upsert(
                batch,
                on_conflict='key'
            ).execute()
            
            print(f"   ✅ Batch {batch_num}/{total_batches}: Inserted {len(batch)} entries")
        
        except Exception as e:
            print(f"   ❌ Batch {batch_num}/{total_batches} failed: {e}")
            print(f"   Continuing with next batch...")
            continue
    
    print(f"\n🎉 Migration complete! {total_rows} entries processed.")


def verify_migration(expected_count: int) -> None:
    """Verify that the migration was successful."""
    try:
        supabase = get_supabase_client()
        result = supabase.table('stagehand_cache').select('key', count='exact').execute()
        
        actual_count = result.count
        print(f"\n🔍 Verification:")
        print(f"   Expected: {expected_count} entries")
        print(f"   Actual:   {actual_count} entries")
        
        if actual_count == expected_count:
            print(f"   ✅ All entries migrated successfully!")
        elif actual_count > 0:
            print(f"   ⚠️  Count mismatch - please check the stagehand_cache table")
        else:
            print(f"   ❌ No entries found in stagehand_cache table")
    
    except Exception as e:
        print(f"   ❌ Verification failed: {e}")


def main():
    """Main migration process."""
    print("=" * 60)
    print("Cache Migration: JSON → Supabase")
    print("=" * 60)
    
    # Step 1: Load JSON cache
    print("\n📖 Step 1: Loading cache.json...")
    cache_data = load_json_cache()
    
    # Step 2: Transform to Supabase format
    print("\n🔄 Step 2: Transforming data...")
    rows = transform_to_supabase_rows(cache_data)
    print(f"   ✅ Prepared {len(rows)} rows for insertion")
    
    # Show sample of what will be migrated
    print(f"\n📋 Sample entries:")
    for i, row in enumerate(rows[:3]):
        print(f"   {i+1}. {row['key'][:40]}... [{row['cache_type']}]")
    if len(rows) > 3:
        print(f"   ... and {len(rows) - 3} more")
    
    # Step 3: Confirm before proceeding
    print("\n⚠️  This will insert all cache entries into Supabase.")
    response = input("   Continue? (y/N): ").strip().lower()
    
    if response != 'y':
        print("\n❌ Migration cancelled.")
        sys.exit(0)
    
    # Step 4: Migrate to Supabase
    migrate_to_supabase(rows)
    
    # Step 5: Verify
    verify_migration(len(rows))
    
    print("\n" + "=" * 60)
    print("✅ Migration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Verify data in Supabase dashboard")
    print("  2. Deploy updated code to Cloud Run")
    print("  3. (Optional) Backup and remove cache/cache.json")
    print()


if __name__ == "__main__":
    main()

