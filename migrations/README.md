# Cache Migration to Supabase

This directory contains the migration for moving from JSON file-based caching to Supabase database caching for Cloud Run deployment.

## Why Migrate?

The original cache system used `cache/cache.json` which doesn't persist between Cloud Run container instances. Moving to Supabase ensures:
- ✅ Persistent cache across container restarts
- ✅ Shared cache state (if scaling to multiple instances later)
- ✅ No local filesystem dependencies

## Migration Steps

### Step 1: Create the Supabase Table

Run the SQL migration in your Supabase SQL Editor:

```bash
# Copy the contents of 001_create_cache_table.sql
# Paste and run in Supabase Dashboard → SQL Editor
```

Or use the Supabase CLI:

```bash
supabase db push
```

### Step 2: Verify Environment Variables

Ensure your `.env` file has:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

### Step 3: Run the Migration Script

From the project root:

```bash
python migrate_cache_to_supabase.py
```

This will:
1. Read `cache/cache.json`
2. Transform each entry to Supabase format
3. Bulk insert into the `cache` table
4. Verify the migration

Expected output:
```
============================================================
Cache Migration: JSON → Supabase
============================================================

📖 Step 1: Loading cache.json...
✅ Loaded 1005 entries from cache/cache.json

🔄 Step 2: Transforming data...
   ✅ Prepared 1005 rows for insertion

📋 Sample entries:
   1. dom_hash_2fba88e65934 [dom_hash]
   2. last_link_2fba88e65934 [last_link]
   3. dom_hash_818b35ac021f [dom_hash]
   ... and 1002 more

⚠️  This will insert all cache entries into Supabase.
   Continue? (y/N): y

📤 Migrating 1005 cache entries to Supabase...
   ✅ Batch 1/11: Inserted 100 entries
   ✅ Batch 2/11: Inserted 100 entries
   ...

🎉 Migration complete! 1005 entries processed.

🔍 Verification:
   Expected: 1005 entries
   Actual:   1005 entries
   ✅ All entries migrated successfully!
```

### Step 4: Verify in Supabase Dashboard

1. Go to Supabase Dashboard → Table Editor
2. Open the `cache` table
3. Confirm you see all migrated entries

### Step 5: Deploy to Cloud Run

The updated code will now use Supabase for caching:

```bash
# Your existing deployment commands
gcloud run deploy scroopy-agent \
  --source . \
  --region us-central1
```

### Step 6: (Optional) Archive JSON Cache

Once verified working in production:

```bash
# Backup the JSON cache
cp cache/cache.json cache/cache.json.backup

# Optionally remove it (it won't be used anymore)
# rm cache/cache.json
```

## Cache Table Schema

```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,           -- e.g., "dom_hash_abc123"
    value JSONB NOT NULL,            -- Cached data (string, object, array)
    cache_type TEXT NOT NULL,        -- "dom_hash", "link_extraction", etc.
    url_hash TEXT,                   -- Hash of source URL
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
```

### Cache Types

| Type | Description | Value Type |
|------|-------------|------------|
| `dom_hash` | Hash of page DOM content | String (16 chars) |
| `last_link` | Last extracted article link | String (URL) |
| `link_extraction` | Extracted article link | String (URL) |
| `article_extraction` | Full article data | Object (title, author, content, date) |

## Troubleshooting

### Migration fails with "environment variables required"

**Problem:** Supabase credentials not found

**Solution:**
```bash
# Check your .env file exists and has:
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### Migration completes but verification shows 0 entries

**Problem:** Network issue or permissions problem

**Solution:**
1. Check your Supabase service role key has write permissions
2. Verify network connectivity to Supabase
3. Check Supabase logs for errors

### Cache reads fail in production

**Problem:** Environment variables not set in Cloud Run

**Solution:**
```bash
# Set environment variables in Cloud Run
gcloud run services update scroopy-agent \
  --set-env-vars SUPABASE_URL=https://... \
  --set-env-vars SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### "Table 'cache' does not exist"

**Problem:** SQL migration not run

**Solution:**
1. Open Supabase Dashboard → SQL Editor
2. Run `001_create_cache_table.sql`
3. Verify table appears in Table Editor

## Rollback (Emergency)

If you need to rollback to JSON caching:

1. Restore the old `stagehand_cache.py` from git:
```bash
git checkout HEAD~1 -- src/utils/stagehand_cache.py
```

2. Redeploy to Cloud Run

Note: The JSON cache won't work correctly in Cloud Run (it's ephemeral), but it will work for local development.

## Performance Considerations

- **Latency:** Supabase queries add ~20-100ms per cache operation vs local JSON
- **Benefits:** This is acceptable given cache hits save 3-10 seconds of scraping
- **Optimization:** Cache table is indexed on `key`, `cache_type`, and `url_hash`

## Future Enhancements

Possible improvements (not currently implemented):

- **TTL/Expiration:** Add `expires_at` column for automatic cache invalidation
- **Cache Statistics:** Track hit/miss rates for optimization
- **Batch Operations:** Batch multiple cache reads/writes
- **Connection Pooling:** If scaling to many instances, tune connection pool settings

