"""
Phase 4 — Text-to-SQL Agent
The brain of the system. Orchestrates:
  1. Schema retrieval (find relevant tables)
  2. SQL generation (Groq LLM with few-shot prompt)
  3. SQL validation (safety + syntax)
  4. Query execution (via db_connector)
  5. Result narration (LLM explains the data)
  6. Chart type detection (bar / line / pie / none)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.exc import SQLAlchemyError

from backend.config import config
from backend.db_connector import DatabaseConnector
from backend.schema_retriever import (
    retrieve_relevant_schemas,
    ensure_index_exists,
    NORTHWIND_COLLECTION,
)
from backend.sql_validator import validate_and_sanitize

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Typed response from the Text-to-SQL agent."""
    question: str
    sql: str
    result_df: pd.DataFrame
    narration: str
    chart_type: str          # "bar" | "line" | "pie" | "none"
    error: str = ""
    retries: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict (DataFrame → list of records)."""
        return {
            "question": self.question,
            "sql": self.sql,
            "result": self.result_df.to_dict(orient="records"),
            "columns": list(self.result_df.columns),
            "narration": self.narration,
            "chart_type": self.chart_type,
            "error": self.error,
            "retries": self.retries,
            "latency_ms": round(self.latency_ms, 1),
            "row_count": len(self.result_df),
        }


# ──────────────────────────────────────────────
# Prompt construction
# ──────────────────────────────────────────────

def _get_system_prompt(dialect: str = "sqlite") -> str:
    """Return the SQL generation system prompt, adapted for the DB dialect.

    Args:
        dialect: Database dialect name (sqlite, postgresql, mysql).

    Returns:
        System prompt string.
    """
    dialect_label = {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
    }.get(dialect, dialect.upper())

    return (
        f"You are an expert SQL analyst working with a {dialect_label} database.\n"
        "Your job is to write a single, correct SELECT statement given a database schema "
        "and a user question.\n"
        "You must follow the rules exactly. Return ONLY the SQL query — no explanation, "
        "no markdown, no preamble."
    )


_SQL_FEW_SHOTS_SQLITE = """
<examples>
Question: What are the top 5 customers by total order value?
SQL: SELECT c.CompanyName, ROUND(SUM(od.UnitPrice * od.Quantity), 2) AS TotalValue FROM Customers c JOIN Orders o ON c.CustomerID = o.CustomerID JOIN "Order Details" od ON o.OrderID = od.OrderID GROUP BY c.CustomerID, c.CompanyName ORDER BY TotalValue DESC LIMIT 5

Question: How many orders were placed each month in 1997?
SQL: SELECT strftime('%m', OrderDate) AS Month, COUNT(*) AS OrderCount FROM Orders WHERE strftime('%Y', OrderDate) = '1997' GROUP BY Month ORDER BY Month

Question: Which employees have processed more than 50 orders?
SQL: SELECT e.FirstName || ' ' || e.LastName AS EmployeeName, COUNT(o.OrderID) AS OrderCount FROM Employees e JOIN Orders o ON e.EmployeeID = o.EmployeeID GROUP BY e.EmployeeID HAVING OrderCount > 50 ORDER BY OrderCount DESC
</examples>"""


_SQL_FEW_SHOTS_POSTGRES = """
<examples>
Question: What are the top 5 customers by total order value?
SQL: SELECT c."CompanyName", ROUND(SUM(od."UnitPrice" * od."Quantity")::numeric, 2) AS "TotalValue" FROM "Customers" c JOIN "Orders" o ON c."CustomerID" = o."CustomerID" JOIN "Order Details" od ON o."OrderID" = od."OrderID" GROUP BY c."CustomerID", c."CompanyName" ORDER BY "TotalValue" DESC LIMIT 5

Question: How many orders were placed each month in 1997?
SQL: SELECT EXTRACT(MONTH FROM "OrderDate")::int AS "Month", COUNT(*) AS "OrderCount" FROM "Orders" WHERE EXTRACT(YEAR FROM "OrderDate") = 1997 GROUP BY "Month" ORDER BY "Month"

Question: Which employees have processed more than 50 orders?
SQL: SELECT e."FirstName" || ' ' || e."LastName" AS "EmployeeName", COUNT(o."OrderID") AS "OrderCount" FROM "Employees" e JOIN "Orders" o ON e."EmployeeID" = o."EmployeeID" GROUP BY e."EmployeeID", e."FirstName", e."LastName" HAVING COUNT(o."OrderID") > 50 ORDER BY "OrderCount" DESC
</examples>"""


def _get_dialect_rules(dialect: str = "sqlite") -> str:
    """Return dialect-specific SQL rules for the generation prompt.

    Args:
        dialect: Database dialect name.

    Returns:
        Rules string.
    """
    common = [
        "- Write ONLY a single SELECT statement. Never use DROP, DELETE, UPDATE, INSERT, ALTER, or TRUNCATE.",
        "- Use explicit JOIN ... ON syntax, never implicit comma joins.",
        "- For currency/price calculations, wrap in ROUND(..., 2).",
        "- Return ONLY the SQL query. No explanation. No markdown. No semicolon at the end.",
        f"- Always use LIMIT {config.result_limit} unless the question asks for all records.",
    ]

    if dialect == "postgresql":
        specific = [
            '- For date filtering, use EXTRACT(YEAR FROM "DateCol") = 1997.',
            "- Use double quotes for column/table names that need quoting.",
            "- For type casting, use :: syntax (e.g. value::numeric).",
            "- Use CONCAT() or || for string concatenation.",
        ]
    elif dialect == "mysql":
        specific = [
            "- For date filtering, use YEAR(DateCol) = 1997, MONTH(DateCol), etc.",
            "- Use backticks for quoting identifiers: `table_name`.",
            "- Use CONCAT() for string concatenation.",
        ]
    else:  # sqlite
        specific = [
            "- Use table aliases (e.g. o for Orders, od for \"Order Details\", c for Customers).",
            '- Wrap table names that contain spaces in double quotes: "Order Details".',
            "- For date filtering, use SQLite functions: strftime('%Y', OrderDate) = '1997'.",
        ]

    return "\n".join(common + specific)


def _get_few_shots(dialect: str = "sqlite") -> str:
    """Return few-shot examples for the given dialect."""
    if dialect == "postgresql":
        return _SQL_FEW_SHOTS_POSTGRES
    return _SQL_FEW_SHOTS_SQLITE


def build_sql_prompt(
    question: str,
    schema: str,
    error: str = "",
    prev_sql: str = "",
    dialect: str = "sqlite",
) -> str:
    """Build the full structured SQL generation prompt.

    Uses chain-of-thought framing, few-shot examples, and optional
    error feedback for the self-correction retry loop.

    Args:
        question: User's natural language question.
        schema: Relevant table schemas (from schema_retriever).
        error: Error message from previous attempt (empty on first try).
        prev_sql: SQL from previous failed attempt.
        dialect: Database dialect for dialect-specific rules.

    Returns:
        Formatted prompt string for the LLM.
    """
    error_context = ""
    if error and prev_sql:
        error_context = f"""
<previous_attempt>
The previous SQL failed with this error: {error}
Previous SQL: {prev_sql}
Analyze the error, fix it, and generate corrected SQL.
</previous_attempt>
"""

    rules = _get_dialect_rules(dialect)
    few_shots = _get_few_shots(dialect)

    return f"""<database_schema>
{schema}
</database_schema>

<rules>
{rules}
</rules>

{few_shots}
{error_context}
Question: {question}
SQL:"""


def detect_chart_type(df: pd.DataFrame) -> str:
    """Heuristically determine the best chart type for the result."""
    if df.empty:
        return "none"

    col_names_lower = [c.lower() for c in df.columns]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # 1. KPI (1 row, exactly 1 numeric column)
    if len(df) == 1 and len(numeric_cols) == 1 and len(df.columns) <= 2:
        return "kpi"

    if len(df.columns) < 2 or not numeric_cols:
        return "none"

    # 2. Scatter / Map (contains lat and lon)
    geo_keywords_lat = ["lat", "latitude"]
    geo_keywords_lon = ["lon", "longitude", "lng"]
    has_lat = any(kw in col_names_lower for kw in geo_keywords_lat)
    has_lon = any(kw in col_names_lower for kw in geo_keywords_lon)
    if has_lat and has_lon:
        return "scatter"

    # 3. Line (Date/Time + Numeric)
    date_keywords = ["date", "month", "year", "week", "day", "quarter", "time"]
    first_col = col_names_lower[0]
    is_time = any(kw in first_col for kw in date_keywords)

    if is_time and len(numeric_cols) >= 1:
        return "line"

    # 4. Pie (Small categories + numeric)
    if len(df) <= 8 and len(df.columns) == 2:
        return "pie"

    # 5. Bar (Default)
    return "bar"


# ──────────────────────────────────────────────
# Agent class
# ──────────────────────────────────────────────

class TextToSQLAgent:
    """Orchestrates the full Text-to-SQL pipeline.

    Supports querying against any data source by accepting a db_connector
    and collection_name per-request. Falls back to the default Northwind
    database if no source is specified.
    """

    def __init__(self):
        # Default DB connector (Northwind) — None if no local DB
        self.default_db: Optional[DatabaseConnector] = None
        if config.db_path:
            self.default_db = DatabaseConnector(config.db_path)
            # Build schema index at startup if not already built
            ensure_index_exists(self.default_db, NORTHWIND_COLLECTION, config.embedding_model)

        self.llm = ChatGroq(
            api_key=config.groq_api_key,
            model=config.groq_model,
            temperature=0,         # Deterministic SQL generation
            max_tokens=1024,
        )
        logger.info("TextToSQLAgent initialized.")

    def _call_llm(self, system: str, user: str) -> str:
        """Call the Groq LLM and return the response text.

        Args:
            system: System prompt string.
            user: User message string.

        Returns:
            LLM response text (stripped).
        """
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        response = self.llm.invoke(messages)
        return response.content.strip()

    def generate_sql(
        self,
        question: str,
        collection_name: str = NORTHWIND_COLLECTION,
        dialect: str = "sqlite",
    ) -> str:
        """Generate SQL from a question using schema retrieval + LLM.

        Args:
            question: User's natural language question.
            collection_name: Chroma collection to retrieve schemas from.
            dialect: Database dialect for prompt rules.

        Returns:
            Raw SQL string from the LLM (not yet validated).
        """
        schema = retrieve_relevant_schemas(
            question,
            collection_name=collection_name,
            embedding_model=config.embedding_model,
            top_k=config.top_k_tables,
        )
        prompt = build_sql_prompt(question, schema, dialect=dialect)
        system_prompt = _get_system_prompt(dialect)
        raw_sql = self._call_llm(system_prompt, prompt)
        logger.info(f"LLM generated SQL: {raw_sql[:120]}")
        return raw_sql

    def narrate_result(self, question: str, sql: str, df: pd.DataFrame) -> str:
        """Ask the LLM to explain query results in plain English.

        Args:
            question: Original user question.
            sql: The SQL that was executed.
            df: Query result DataFrame (first 10 rows used for context).

        Returns:
            2-3 sentence natural language answer.
        """
        if df.empty:
            return "The query returned no results. Try rephrasing your question."

        # Pass top 10 rows as context to keep tokens manageable
        sample = df.head(10).to_string(index=False)

        prompt = f"""The user asked: "{question}"

The SQL query used:
{sql}

The query returned {len(df)} row(s). Here is a sample:
{sample}

Write a 2-3 sentence plain English answer to the user's question based on these results.
Be specific — mention actual values, names, or numbers from the data.
Do not explain the SQL. Just answer the question naturally."""

        return self._call_llm(
            "You are a helpful data analyst. Summarize query results clearly and concisely.",
            prompt,
        )

    def answer(
        self,
        question: str,
        db_connector: Optional[DatabaseConnector] = None,
        collection_name: str = NORTHWIND_COLLECTION,
    ) -> AgentResponse:
        """Run the full pipeline: question → SQL → execute → narrate.

        Includes retry loop with LLM self-correction on SQL errors.

        Args:
            question: User's natural language question.
            db_connector: DatabaseConnector for the target data source.
                          Defaults to the built-in Northwind connector.
            collection_name: Chroma collection name for schema retrieval.

        Returns:
            AgentResponse with SQL, results, narration, and chart type.
        """
        db = db_connector or self.default_db
        if db is None:
            return AgentResponse(
                question=question,
                sql="",
                result_df=pd.DataFrame(),
                narration="",
                chart_type="none",
                error="No database configured. Upload a CSV or connect a database first.",
            )

        dialect = db.get_dialect_name()
        system_prompt = _get_system_prompt(dialect)

        start = time.time()
        retries = 0
        last_error = ""
        last_sql = ""

        for attempt in range(config.max_retries):
            # On retries, include the previous error in the prompt
            try:
                schema = retrieve_relevant_schemas(
                    question,
                    collection_name=collection_name,
                    embedding_model=config.embedding_model,
                    top_k=config.top_k_tables,
                )
            except ValueError as e:
                if "not found" in str(e).lower() and db is not None:
                    logger.warning(f"Chroma collection missing on query. Rebuilding {collection_name} on the fly...")
                    try:
                        ensure_index_exists(db, collection_name, config.embedding_model)
                        schema = retrieve_relevant_schemas(
                            question,
                            collection_name=collection_name,
                            embedding_model=config.embedding_model,
                            top_k=config.top_k_tables,
                        )
                    except ValueError as inner_e:
                        logger.error(f"Failed to auto-rebuild schema: {inner_e}")
                        return AgentResponse(
                            question=question,
                            sql="",
                            result_df=pd.DataFrame(),
                            narration="",
                            chart_type="none",
                            error=str(inner_e)
                        )
                else:
                    raise e
            prompt = build_sql_prompt(
                question, schema, last_error, last_sql, dialect=dialect
            )
            raw_sql = self._call_llm(system_prompt, prompt)

            is_valid, clean_sql, validation_error = validate_and_sanitize(
                raw_sql, dialect=dialect
            )

            if not is_valid:
                last_error = validation_error
                last_sql = clean_sql
                retries += 1
                logger.warning(f"Attempt {attempt+1} validation failed: {validation_error}")
                continue

            # Validated — try execution
            try:
                df = db.run_query(clean_sql)
                narration = self.narrate_result(question, clean_sql, df)
                chart_type = detect_chart_type(df)
                latency = (time.time() - start) * 1000

                return AgentResponse(
                    question=question,
                    sql=clean_sql,
                    result_df=df,
                    narration=narration,
                    chart_type=chart_type,
                    retries=retries,
                    latency_ms=latency,
                )

            except (SQLAlchemyError, TimeoutError) as e:
                last_error = str(e)
                last_sql = clean_sql
                retries += 1
                logger.warning(f"Attempt {attempt+1} execution failed: {e}")
                continue

        # All retries exhausted
        latency = (time.time() - start) * 1000
        return AgentResponse(
            question=question,
            sql=last_sql,
            result_df=pd.DataFrame(),
            narration="",
            chart_type="none",
            error=f"Could not generate valid SQL after {config.max_retries} attempts. Last error: {last_error}",
            retries=retries,
            latency_ms=latency,
        )

    def generate_sample_questions(self, db_connector: DatabaseConnector) -> list[str]:
        """Generate dynamic sample questions based on the schema."""
        try:
            schema = db_connector.get_full_schema_ddl()
            # truncate schema if it's too huge
            schema = schema[:4000]
            prompt = f"Given the following database schema, generate 4 distinct, analytical, and interesting sample questions a user could ask.\n\nSchema:\n{schema}\n\nReturn EXACTLY 4 questions separated by newlines, with no numbering, bullet points, or extra text."
            
            system_prompt = "You are an expert data analyst. Return ONLY the questions as plain text, one per line."
            response = self._call_llm(system_prompt, prompt)
            
            questions = [q.strip("- *1234567890.") for q in response.split("\n") if q.strip()]
            return questions[:4] if len(questions) >= 4 else questions
        except Exception as e:
            logger.error(f"Failed to generate sample questions: {e}")
            return []

