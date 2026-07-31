"""
Phase 3 — SQL Validator
Runs before ANY query reaches the database.

Responsibilities:
  1. sanitize_sql()  — clean up LLM output formatting artifacts
  2. validate_sql()  — block dangerous ops and catch syntax errors
  3. inject_limit()  — enforce row-limit cap if no LIMIT is present
  4. validate_and_sanitize() — convenience wrapper for the full pipeline
"""

import re
import logging
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DDL, DML

logger = logging.getLogger(__name__)

# Maximum rows any query may return (safety cap)
MAX_ROW_LIMIT = 10_000

# Operations that must never reach the database
FORBIDDEN_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "TRUNCATE", "CREATE", "EXEC", "EXECUTE", "GRANT",
    "REVOKE", "REPLACE", "MERGE", "CALL",
    "COPY", "LOAD", "VACUUM",
}

# Dangerous patterns — dialect-agnostic
DANGEROUS_PATTERNS = [
    r"xp_\w+",                    # MSSQL extended procs
    r"ATTACH\s+DATABASE",         # SQLite: attach another DB file
    r"DETACH\s+DATABASE",         # SQLite: detach DB
    r"PRAGMA\s+",                 # SQLite: pragma commands
    r"SET\s+",                    # Postgres/MySQL: SET commands
    r"COPY\s+",                   # Postgres: COPY command
    r"\\copy",                    # psql meta-command
    r"LOAD\s+DATA",              # MySQL: LOAD DATA INFILE
    r"/\*.*?\*/",                 # Block comment injection
    r";\s*\w",                    # Stacked queries (second statement after semicolon)
    r";\s*$",                     # Trailing semicolon before end (caught by sanitize, but double-check)
    r"INTO\s+OUTFILE",           # MySQL: write to file
    r"INTO\s+DUMPFILE",          # MySQL: write to file
]

# Standalone comment patterns — checked separately because `--` in strings
# like 'some--value' is benign, but `-- comment` at statement level is not.
COMMENT_PATTERN = re.compile(
    r"--(?!\s*\d)",  # -- followed by non-digit (allow `--` in expressions but block comment injection)
    re.IGNORECASE,
)


def sanitize_sql(raw: str) -> str:
    """Strip LLM output artifacts and normalize the SQL string.

    LLMs often return SQL wrapped in markdown fences, with extra commentary,
    or with trailing semicolons that SQLAlchemy doesn't need.

    Args:
        raw: Raw string from the LLM output.

    Returns:
        Clean SQL string, ready for validation and execution.
    """
    sql = raw.strip()

    # Strip markdown fences: ```sql ... ``` or ``` ... ```
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)

    # Strip common LLM preambles like "Here is the SQL:" or "SQL:"
    sql = re.sub(r"^(?:here(?:'s| is)(?: the)? (?:sql|query)[:\s]*)", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^(?:sql|query)\s*:\s*", "", sql, flags=re.IGNORECASE)

    # Collapse multiple whitespace
    sql = " ".join(sql.split())

    # Remove trailing semicolon (SQLAlchemy adds it internally)
    sql = sql.rstrip(";").strip()

    return sql


def inject_limit(sql: str, max_limit: int = MAX_ROW_LIMIT, dialect: str = "sqlite") -> str:
    """Inject or cap a LIMIT clause to prevent runaway queries.

    If the query already has a LIMIT, cap it at max_limit.
    If no LIMIT is present, append one.

    Args:
        sql: Sanitized SQL string.
        max_limit: Maximum number of rows to allow.
        dialect: Database dialect (sqlite, postgresql, mysql).

    Returns:
        SQL string with a LIMIT clause guaranteed to be ≤ max_limit.
    """
    sql_upper = sql.upper()

    # Check if LIMIT already exists (handle LIMIT N and LIMIT N OFFSET M)
    limit_match = re.search(
        r"\bLIMIT\s+(\d+)",
        sql_upper,
    )

    if limit_match:
        existing_limit = int(limit_match.group(1))
        if existing_limit > max_limit:
            # Cap the existing LIMIT
            sql = re.sub(
                r"\bLIMIT\s+\d+",
                f"LIMIT {max_limit}",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
            logger.info(f"Capped LIMIT from {existing_limit} to {max_limit}")
        return sql

    # No LIMIT found — inject one
    # Handle ORDER BY + potential OFFSET at the end
    sql = f"{sql} LIMIT {max_limit}"
    logger.debug(f"Injected LIMIT {max_limit}")
    return sql


def _check_multi_statement(sql: str) -> bool:
    """Check if the SQL contains multiple statements (stacked queries).

    More robust than regex — uses sqlparse to split statements.

    Args:
        sql: SQL string to check.

    Returns:
        True if multiple statements detected.
    """
    statements = sqlparse.split(sql)
    # Filter out empty strings
    non_empty = [s.strip() for s in statements if s.strip()]
    return len(non_empty) > 1


def validate_sql(sql: str, dialect: str = "sqlite") -> tuple[bool, str]:
    """Validate a SQL string for safety and basic syntax correctness.

    Checks performed (in order):
      1. Empty string check
      2. Must start with SELECT (or WITH for CTEs)
      3. Multi-statement detection (stacked queries)
      4. No forbidden DDL/DML keywords (DROP, DELETE, UPDATE, etc.)
      5. No dangerous patterns (comment injection, file access, etc.)
      6. Balanced parentheses
      7. sqlparse structural parse (catches gross syntax errors)

    Args:
        sql: Sanitized SQL string (run sanitize_sql first).
        dialect: Database dialect name (sqlite, postgresql, mysql).

    Returns:
        Tuple of (is_valid: bool, error_message: str).
        error_message is empty string when is_valid is True.
    """
    # 1. Empty check
    if not sql or not sql.strip():
        return False, "SQL is empty."

    sql_upper = sql.upper().strip()

    # 2. Must start with SELECT or WITH (CTEs are valid)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False, (
            f"Only SELECT statements are allowed. "
            f"Got: '{sql.split()[0] if sql.split() else 'empty'}'"
        )

    # 3. Multi-statement detection
    if _check_multi_statement(sql):
        return False, (
            "Multiple SQL statements detected. "
            "Only a single SELECT statement is allowed."
        )

    # 4. Check for forbidden keywords using word-boundary matching
    #    to avoid false positives ("DELETED_AT" contains "DELETE")
    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, sql_upper):
            return False, (
                f"Forbidden operation '{keyword}' is not allowed. "
                f"Only SELECT queries are permitted."
            )

    # 5. Dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, sql, flags=re.IGNORECASE | re.DOTALL):
            return False, f"Dangerous SQL pattern detected."

    # 5b. Comment injection check (separate from pattern list for nuance)
    if COMMENT_PATTERN.search(sql):
        return False, "SQL comments are not allowed in generated queries."

    # 6. Balanced parentheses
    open_count = sql.count("(")
    close_count = sql.count(")")
    if open_count != close_count:
        return False, (
            f"Unbalanced parentheses: {open_count} opening vs {close_count} closing."
        )

    # 7. sqlparse structural check
    try:
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False, "sqlparse could not parse this SQL."
        stmt: Statement = parsed[0]
        stmt_type = stmt.get_type()
        if stmt_type and stmt_type.upper() not in ("SELECT", "UNKNOWN"):
            # UNKNOWN is sometimes returned for CTEs — that's acceptable
            return False, f"Statement type must be SELECT, got: {stmt_type}"
    except Exception as e:
        return False, f"SQL parse error: {e}"

    logger.debug(f"SQL passed validation: {sql[:80]}...")
    return True, ""


def validate_and_sanitize(
    raw_sql: str,
    dialect: str = "sqlite",
    max_limit: int = MAX_ROW_LIMIT,
) -> tuple[bool, str, str]:
    """Convenience function: sanitize → validate → inject limit.

    Args:
        raw_sql: Raw LLM output string.
        dialect: Database dialect (sqlite, postgresql, mysql).
        max_limit: Maximum row limit to enforce.

    Returns:
        Tuple of (is_valid: bool, clean_sql: str, error_message: str).
        If invalid, clean_sql is the sanitized (but invalid) SQL for logging.
        If valid, clean_sql has the LIMIT injected/capped.
    """
    clean = sanitize_sql(raw_sql)
    is_valid, error = validate_sql(clean, dialect=dialect)
    if not is_valid:
        logger.warning(f"SQL validation failed: {error} | SQL: {clean[:120]}")
        return is_valid, clean, error

    # Inject/cap LIMIT on valid queries
    clean = inject_limit(clean, max_limit=max_limit, dialect=dialect)
    return True, clean, ""

