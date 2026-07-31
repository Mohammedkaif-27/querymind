-- ============================================================
-- Migration 002: Dashboards Schema
-- Sets up dashboards and dashboard_widgets tables.
-- Run this in Supabase SQL Editor.
-- ============================================================

-- 1. dashboards — tracks user dashboards
CREATE TABLE IF NOT EXISTS public.dashboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dashboards_user_id ON public.dashboards(user_id);

-- 2. dashboard_widgets — saved charts and queries
CREATE TABLE IF NOT EXISTS public.dashboard_widgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id UUID NOT NULL REFERENCES public.dashboards(id) ON DELETE CASCADE,
    source_id UUID REFERENCES public.data_sources(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    chart_type TEXT NOT NULL DEFAULT 'table',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard_id ON public.dashboard_widgets(dashboard_id);

-- 3. Row-Level Security — users can only see their own dashboards
-- dashboards
ALTER TABLE public.dashboards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own dashboards"
    ON public.dashboards FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own dashboards"
    ON public.dashboards FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own dashboards"
    ON public.dashboards FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own dashboards"
    ON public.dashboards FOR DELETE
    USING (auth.uid() = user_id);

-- dashboard_widgets
ALTER TABLE public.dashboard_widgets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own dashboard widgets"
    ON public.dashboard_widgets FOR SELECT
    USING (
        dashboard_id IN (
            SELECT id FROM public.dashboards WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert own dashboard widgets"
    ON public.dashboard_widgets FOR INSERT
    WITH CHECK (
        dashboard_id IN (
            SELECT id FROM public.dashboards WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update own dashboard widgets"
    ON public.dashboard_widgets FOR UPDATE
    USING (
        dashboard_id IN (
            SELECT id FROM public.dashboards WHERE user_id = auth.uid()
        )
    )
    WITH CHECK (
        dashboard_id IN (
            SELECT id FROM public.dashboards WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete own dashboard widgets"
    ON public.dashboard_widgets FOR DELETE
    USING (
        dashboard_id IN (
            SELECT id FROM public.dashboards WHERE user_id = auth.uid()
        )
    );
