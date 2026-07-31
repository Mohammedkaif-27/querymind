"""
Supabase Client
Singleton Supabase client using the service_role key for backend operations.
The service role key bypasses RLS — the backend enforces user scoping in code,
and RLS acts as defense-in-depth for any direct frontend access.
"""

import logging
from supabase import create_client, Client

from backend.config import config

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase_client() -> Client:
    """Return the singleton Supabase client (service role).

    Uses the service_role key, which bypasses RLS. This is intentional:
    the backend is the trusted intermediary and enforces user scoping in
    its own code. RLS protects against direct Supabase client access.

    Returns:
        Supabase Client instance.
    """
    global _client
    if _client is None:
        _client = create_client(
            config.supabase_url,
            config.supabase_service_role_key,
        )
        logger.info("Supabase client initialized (service role).")
    return _client
