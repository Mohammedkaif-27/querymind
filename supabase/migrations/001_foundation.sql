-- ============================================================
-- Migration 001: Foundation Schema
-- Sets up data_sources, query_history, user_data schema,
-- Row-Level Security policies, and storage bucket.
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor).
-- ============================================================

-- 1. Create a dedicated schema for user-uploaded table data
--    Uploaded CSVs will be stored as tables here: user_data.src_<source_id>
CREATE SCHEMA IF NOT EXISTS user_data;

-- 2. data_sources — tracks every connected data source per user
CREATE TABLE IF NOT EXISTS public.data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('csv', 'xlsx', 'postgres', 'mysql')),
    connection_info JSONB DEFAULT '{}'::jsonb,
    chroma_collection_name TEXT NOT NULL,
    schema_hash TEXT,
    table_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast user-scoped lookups
CREATE INDEX IF NOT EXISTS idx_data_sources_user_id ON public.data_sources(user_id);

-- 3. query_history — log of every query attempt per user
CREATE TABLE IF NOT EXISTS public.query_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES public.data_sources(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    generated_sql TEXT DEFAULT '',
    success BOOLEAN DEFAULT false,
    latency_ms REAL DEFAULT 0,
    row_count INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_query_history_user_id ON public.query_history(user_id);
CREATE INDEX IF NOT EXISTS idx_query_history_source_id ON public.query_history(source_id);

-- 4. Row-Level Security — users can only see their own rows
-- data_sources
ALTER TABLE public.data_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own sources"
    ON public.data_sources FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sources"
    ON public.data_sources FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sources"
    ON public.data_sources FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own sources"
    ON public.data_sources FOR DELETE
    USING (auth.uid() = user_id);

-- query_history
ALTER TABLE public.query_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own history"
    ON public.query_history FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own history"
    ON public.query_history FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- 5. Service role bypass — the FastAPI backend uses the service_role key,
--    which bypasses RLS. RLS protects against direct Supabase client access
--    from the frontend (anon key). The backend enforces user scoping in code
--    AND RLS acts as a defense-in-depth layer.

-- 6. Storage bucket for raw uploaded files
-- NOTE: Run this via the Supabase Dashboard → Storage → New Bucket,
-- or use the SQL below (requires the storage extension to be enabled):
INSERT INTO storage.buckets (id, name, public)
VALUES ('raw-uploads', 'raw-uploads', false)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS: users can only access files in their own folder
-- Files are stored as: raw-uploads/<user_id>/<filename>
CREATE POLICY "Users can upload to own folder"
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'raw-uploads'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

CREATE POLICY "Users can read own uploads"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'raw-uploads'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

CREATE POLICY "Users can delete own uploads"
    ON storage.objects FOR DELETE
    USING (
        bucket_id = 'raw-uploads'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );
