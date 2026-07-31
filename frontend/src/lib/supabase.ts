import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL =
  import.meta.env.VITE_SUPABASE_URL ||
  'https://sjchqdukavrxdyufxcpg.supabase.co';

const SUPABASE_ANON_KEY =
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNqY2hxZHVrYXZyeGR5dWZ4Y3BnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0MTQ0MjcsImV4cCI6MjEwMDk5MDQyN30.tB_I587lOswiA133xkItMNDeZZO5n6Iuykl0Vr47O-8';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
