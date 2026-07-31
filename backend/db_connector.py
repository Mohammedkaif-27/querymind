"""
Phase 1 — Database Connector
Handles all direct database interactions via SQLAlchemy.
Supports SQLite, PostgreSQL, and MySQL connections.
Other modules never touch the database directly — they go through this module.
"""

import logging
from typing import Optional
import pandas as pd
from sqlalchemy import create_engine, text, inspect, event
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """Manages a database connection and exposes safe query execution.

    Supports SQLite (local files), PostgreSQL (Supabase or external),
    and MySQL connections via SQLAlchemy URIs.
    """

    def __init__(self, db_path: str):
        """Initialize connector from a local SQLite path (legacy interface).

        Args:
            db_path: Absolute path to the SQLite .db file.
        """
        self.db_path = db_path
        self.connection_uri = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.connection_uri,
            connect_args={"check_same_thread": False},
        )
        self._verify_connection()

    @classmethod
    def from_uri(cls, uri: str, schema: Optional[str] = None) -> "DatabaseConnector":
        """Create a connector from any SQLAlchemy connection URI.

        Args:
            uri: SQLAlchemy connection string (e.g. postgresql://..., mysql://..., sqlite:///...).
            schema: Optional schema to use for table introspection (e.g. 'user_data').

        Returns:
            DatabaseConnector instance connected to the given URI.
        """
        instance = object.__new__(cls)
        instance.db_path = uri  # Store URI as db_path for compatibility
        instance.connection_uri = uri
        instance._schema = schema

        engine_kwargs = {}
        if "sqlite" in uri:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        # Use pg8000 driver for PostgreSQL if no specific driver is specified
        if uri.startswith("postgresql://"):
            uri = uri.replace("postgresql://", "postgresql+pg8000://", 1)

        instance.engine = create_engine(uri, **engine_kwargs)

        if schema and "postgresql" in uri:
            target_schema = schema
            @event.listens_for(instance.engine, "connect")
            def set_search_path(dbapi_connection, connection_record):
                try:
                    cursor = dbapi_connection.cursor()
                    cursor.execute(f"SET search_path TO {target_schema}, public")
                    cursor.close()
                except Exception as err:
                    logger.warning(f"Could not set search_path to {target_schema}: {err}")

        instance._verify_connection()
        return instance

    def _verify_connection(self):
        """Run a trivial query to confirm the DB is accessible."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"✅ Connected to database: {self.get_dialect_name()}")
        except SQLAlchemyError as e:
            raise ConnectionError(f"Cannot connect to database: {e}")

    def get_dialect_name(self) -> str:
        """Return the SQL dialect name (sqlite, postgresql, mysql).

        Returns:
            Dialect name string.
        """
        return self.engine.dialect.name

    def run_query(self, sql: str, timeout_seconds: Optional[int] = None) -> pd.DataFrame:
        """Execute a SELECT query and return results as a DataFrame.

        Args:
            sql: A validated SELECT SQL statement.

        Returns:
            pd.DataFrame with query results. Empty DataFrame if no rows.

        Raises:
            SQLAlchemyError: If the query fails at the DB level.
            TimeoutError: If the query exceeds the timeout.
        """
        if timeout_seconds is None:
            import os
            timeout_seconds = int(os.getenv("QUERY_TIMEOUT_SECONDS", "10"))

        try:
            with self.engine.connect() as conn:
                dialect = self.get_dialect_name()

                # Set statement-level timeout based on dialect
                if dialect == "postgresql":
                    conn.execute(
                        text(f"SET LOCAL statement_timeout = '{timeout_seconds * 1000}'")
                    )
                elif dialect == "mysql":
                    conn.execute(
                        text(f"SET SESSION MAX_EXECUTION_TIME = {timeout_seconds * 1000}")
                    )
                # SQLite doesn't support statement_timeout — rely on LIMIT cap

                result = pd.read_sql_query(text(sql), conn)
            logger.info(f"Query returned {len(result)} rows | SQL: {sql[:80]}...")
            return result
        except SQLAlchemyError as e:
            error_str = str(e).lower()
            if "timeout" in error_str or "cancel" in error_str:
                logger.warning(f"Query timed out after {timeout_seconds}s | SQL: {sql[:80]}")
                raise TimeoutError(
                    f"Query timed out after {timeout_seconds} seconds. "
                    "Try simplifying your question."
                ) from e
            logger.error(f"Query failed: {e} | SQL: {sql}")
            raise

    def get_all_table_names(self) -> list[str]:
        """Return names of all tables in the database.

        Returns:
            List of table name strings.
        """
        inspector = inspect(self.engine)
        schema = getattr(self, "_schema", None)
        return inspector.get_table_names(schema=schema)

    def get_table_schema(self, table_name: str) -> str:
        """Return the schema of a single table as a formatted string.

        Format: TableName(col1 TYPE, col2 TYPE, ...)

        Args:
            table_name: Exact name of the table.

        Returns:
            Formatted schema string.
        """
        inspector = inspect(self.engine)
        schema = getattr(self, "_schema", None)
        columns = inspector.get_columns(table_name, schema=schema)
        col_parts = [f"{col['name']} {str(col['type'])}" for col in columns]
        return f"{table_name}({', '.join(col_parts)})"

    def get_table_row_count(self, table_name: str) -> int:
        """Return the number of rows in a table.

        Args:
            table_name: Exact name of the table.

        Returns:
            Integer row count.
        """
        schema = getattr(self, "_schema", None)
        qualified = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {qualified}"))
            return result.scalar()

    def get_all_schemas(self) -> dict[str, str]:
        """Return schemas for all tables as a dict.

        Returns:
            Dict mapping table_name -> schema_string.
        """
        return {
            table: self.get_table_schema(table)
            for table in self.get_all_table_names()
        }

    def get_full_schema_ddl(self) -> str:
        """Return full schema formatted string for all tables."""
        return "\n".join(self.get_all_schemas().values())

    def get_sample_rows(self, table_name: str, n: int = 3) -> pd.DataFrame:
        """Get sample rows from a table.

        Args:
            table_name: Exact name of the table.
            n: Number of sample rows to retrieve.

        Returns:
            DataFrame with sample rows, or empty DataFrame on error.
        """
        schema = getattr(self, "_schema", None)
        qualified = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
        try:
            with self.engine.connect() as conn:
                return pd.read_sql_query(
                    text(f"SELECT * FROM {qualified} LIMIT {n}"), conn
                )
        except Exception as e:
            logger.warning(f"Could not get sample rows for {table_name}: {e}")
            return pd.DataFrame()

    def get_foreign_keys(self, table_name: str) -> list[dict]:
        """Return foreign key relationships for a table.

        Args:
            table_name: Exact name of the table.

        Returns:
            List of FK dicts with 'constrained_columns', 'referred_table', etc.
        """
        inspector = inspect(self.engine)
        schema = getattr(self, "_schema", None)
        try:
            return inspector.get_foreign_keys(table_name, schema=schema)
        except Exception:
            return []

    def create_table_from_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: Optional[str] = None,
        if_exists: str = "replace",
    ) -> int:
        """Write a pandas DataFrame to the database as a table.

        Used for CSV/XLSX ingestion — writes data directly into a DB table.

        Args:
            df: DataFrame to write.
            table_name: Name for the new table.
            schema: Database schema to write to (e.g. 'user_data').
            if_exists: What to do if table exists ('replace', 'append', 'fail').

        Returns:
            Number of rows written.
        """
        if schema:
            try:
                with self.engine.connect() as conn:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
                    conn.commit()
            except Exception:
                pass

        rows = df.to_sql(
            name=table_name,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
        )
        logger.info(
            f"✅ Created table '{schema}.{table_name}' with {len(df)} rows"
            if schema else f"✅ Created table '{table_name}' with {len(df)} rows"
        )
        return len(df)

    def drop_table(self, table_name: str, schema: Optional[str] = None):
        """Drop a table from the database.

        Args:
            table_name: Name of the table to drop.
            schema: Optional schema qualifier.
        """
        qualified = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {qualified}"))
            conn.commit()
        logger.info(f"Dropped table {qualified}")

    def health_check(self) -> dict:
        """Return health status of the DB connection.

        Returns:
            Dict with status, dialect, table_count.
        """
        try:
            tables = self.get_all_table_names()
            return {
                "status": "ok",
                "dialect": self.get_dialect_name(),
                "table_count": len(tables),
                "tables": tables,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

