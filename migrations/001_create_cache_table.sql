-- Migration: Create stagehand_cache table for Supabase
-- This replaces the cache/cache.json file for Cloud Run deployments

-- Create the stagehand_cache table
CREATE TABLE IF NOT EXISTS stagehand_cache (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    cache_type TEXT NOT NULL,
    url_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_stagehand_cache_type ON stagehand_cache(cache_type);
CREATE INDEX IF NOT EXISTS idx_stagehand_cache_url_hash ON stagehand_cache(url_hash);
CREATE INDEX IF NOT EXISTS idx_stagehand_cache_updated_at ON stagehand_cache(updated_at);

-- Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_stagehand_cache_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at on row updates
DROP TRIGGER IF EXISTS stagehand_cache_updated_at_trigger ON stagehand_cache;
CREATE TRIGGER stagehand_cache_updated_at_trigger
    BEFORE UPDATE ON stagehand_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_stagehand_cache_updated_at();

-- Add comment explaining the table
COMMENT ON TABLE stagehand_cache IS 'Cache storage for web scraping operations. Stores DOM hashes, extracted links, and article data.';
COMMENT ON COLUMN stagehand_cache.key IS 'Unique cache key (e.g., dom_hash_abc123, article_extraction_xyz789)';
COMMENT ON COLUMN stagehand_cache.value IS 'Cached value stored as JSONB. Can be string, number, object, or array.';
COMMENT ON COLUMN stagehand_cache.cache_type IS 'Type of cached data: dom_hash, last_link, link_extraction, article_extraction, or action';
COMMENT ON COLUMN stagehand_cache.url_hash IS 'Hash of the source URL for easy querying by URL';

