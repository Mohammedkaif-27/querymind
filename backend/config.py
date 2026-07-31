"""
Phase 1 — Configuration
Loads all environment variables and exposes a typed Config object.
All other modules import from here — never read os.environ directly.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@dataclass
class Config:
    groq_api_key: str
    groq_model: str
    embedding_model: str
    top_k_tables: int
    max_retries: int
    result_limit: int
    # Legacy local DB path — optional, only used for Northwind fallback
    db_path: Optional[str]
    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str
    supabase_db_url: str  # Direct Postgres connection string for SQLAlchemy
    query_timeout_seconds: int  # Max query execution time in seconds

    @classmethod
    def load(cls) -> "Config":
        """Load and validate config from environment variables.

        Returns:
            Config: Populated config object.

        Raises:
            ValueError: If a required environment variable is missing.
        """
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com and add it to your .env file."
            )

        # Supabase config
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
        supabase_db_url = os.getenv("SUPABASE_DB_URL", "")

        if not supabase_url or not supabase_service_role_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required. "
                "Set them in your .env file."
            )

        # Resolve DB path relative to project root (optional for legacy Northwind)
        raw_db_path = os.getenv("DB_PATH", "data/northwind.db")
        project_root = os.path.dirname(os.path.dirname(__file__))
        db_path = os.path.join(project_root, raw_db_path)
        if not os.path.exists(db_path):
            db_path = None  # No local DB — that's fine for Supabase-only mode

        return cls(
            groq_api_key=api_key,
            db_path=db_path,
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            top_k_tables=int(os.getenv("TOP_K_TABLES", "3")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            result_limit=int(os.getenv("RESULT_LIMIT", "100")),
            supabase_url=supabase_url,
            supabase_anon_key=supabase_anon_key,
            supabase_service_role_key=supabase_service_role_key,
            supabase_jwt_secret=supabase_jwt_secret,
            supabase_db_url=supabase_db_url,
            query_timeout_seconds=int(os.getenv("QUERY_TIMEOUT_SECONDS", "10")),
        )


# Singleton — import this everywhere
config = Config.load()

