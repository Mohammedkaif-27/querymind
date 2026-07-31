"""
Phase 6 — Evaluation Harness
Runs a suite of predefined natural language questions against the agent,
validates the generated SQL and results, and produces a markdown report.

Usage:
  python -m eval.run_eval
"""

import os
import json
import time
import logging
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from tabulate import tabulate

# Disable verbose logs for eval
logging.getLogger("backend.agent").setLevel(logging.WARNING)
logging.getLogger("backend.db_connector").setLevel(logging.WARNING)
logging.getLogger("backend.sql_validator").setLevel(logging.ERROR)

from backend.agent import TextToSQLAgent
from backend.config import config


@dataclass
class EvalResult:
    test_id: str
    question: str
    difficulty: str
    success: bool
    latency_ms: float
    retries: int
    sql: str
    row_count: int
    error: str
    failure_reason: str = ""


def check_result(df: pd.DataFrame, check_config: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate the DataFrame against the expected result check."""
    check_type = check_config.get("type")

    if df.empty and check_type != "row_count_gte":
        return False, "Result is empty."

    if check_type == "value_gte":
        col_idx = check_config.get("column_index", 0)
        min_val = check_config.get("min_value", 0)
        if len(df.columns) <= col_idx:
            return False, f"Missing column index {col_idx}"
        try:
            val = pd.to_numeric(df.iloc[0, col_idx])
            if val >= min_val:
                return True, ""
            return False, f"Value {val} < {min_val}"
        except (ValueError, TypeError):
            return False, f"Cannot convert {df.iloc[0, col_idx]} to numeric"

    elif check_type == "column_exists":
        pattern = check_config.get("column_name_pattern", "").lower()
        for col in df.columns:
            if pattern in col.lower():
                return True, ""
        return False, f"No column matching '{pattern}'"

    elif check_type == "has_numeric_column":
        min_cols = check_config.get("min_columns", 1)
        num_cols = len(df.select_dtypes(include="number").columns)
        if num_cols >= min_cols:
            return True, ""
        return False, f"Found {num_cols} numeric columns, expected {min_cols}"
        
    elif check_type == "row_count_gte":
        min_rows = check_config.get("min_rows", 1)
        if len(df) >= min_rows:
            return True, ""
        return False, f"Found {len(df)} rows, expected >= {min_rows}"

    return True, f"Unknown check type: {check_type}"


def run_evaluation():
    """Run all tests in test_cases.json and generate a report."""
    base_dir = os.path.dirname(__file__)
    test_file = os.path.join(base_dir, "test_cases.json")
    report_file = os.path.join(base_dir, "report.md")

    with open(test_file, "r") as f:
        tests = json.load(f)

    print(f"Starting evaluation of {len(tests)} questions against {config.groq_model}...")
    
    agent = TextToSQLAgent()
    results = []

    for idx, test in enumerate(tests, 1):
        print(f"[{idx}/{len(tests)}] {test['id']} - {test['question']}")
        
        # Run agent
        response = agent.answer(test["question"])
        
        success = True
        failure_reason = ""

        # Check 1: Agent reported error
        if response.error:
            success = False
            failure_reason = f"Agent Error: {response.error}"
        else:
            # Check 2: Expected tables used in SQL
            sql_upper = response.sql.upper()
            for table in test.get("expected_tables", []):
                # Simple check: table name exists in query (quotes or not)
                if table.upper() not in sql_upper and f'"{table.upper()}"' not in sql_upper:
                    success = False
                    failure_reason = f"Missing expected table: {table}"
                    break
            
            # Check 3: Row counts
            if success:
                row_count = len(response.result_df)
                if "expected_row_count" in test:
                    if row_count != test["expected_row_count"]:
                        success = False
                        failure_reason = f"Expected {test['expected_row_count']} rows, got {row_count}"
                elif "expected_row_count_range" in test:
                    min_r, max_r = test["expected_row_count_range"]
                    if not (min_r <= row_count <= max_r):
                        success = False
                        failure_reason = f"Expected {min_r}-{max_r} rows, got {row_count}"
            
            # Check 4: Result heuristics
            if success and "result_check" in test:
                pass_check, check_msg = check_result(response.result_df, test["result_check"])
                if not pass_check:
                    success = False
                    failure_reason = f"Data check failed: {check_msg}"

        results.append(EvalResult(
            test_id=test["id"],
            question=test["question"],
            difficulty=test["difficulty"],
            success=success,
            latency_ms=response.latency_ms,
            retries=response.retries,
            sql=response.sql,
            row_count=len(response.result_df) if not response.error else 0,
            error=response.error,
            failure_reason=failure_reason
        ))

        # Sleep briefly to avoid hitting rate limits too hard on free tier
        time.sleep(1.0)

    # ──────────────────────────────────────────────
    # Generate Report
    # ──────────────────────────────────────────────
    
    total = len(results)
    passed = sum(1 for r in results if r.success)
    accuracy = (passed / total) * 100
    avg_latency = sum(r.latency_ms for r in results) / total
    avg_retries = sum(r.retries for r in results) / total
    
    # By difficulty
    diff_stats = {}
    for r in results:
        diff_stats.setdefault(r.difficulty, {"total": 0, "passed": 0})
        diff_stats[r.difficulty]["total"] += 1
        if r.success:
            diff_stats[r.difficulty]["passed"] += 1

    report = [
        "# Text-to-SQL Evaluation Report",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Model:** {config.groq_model}",
        "",
        "## Summary Metrics",
        f"- **Overall Accuracy:** {accuracy:.1f}% ({passed}/{total})",
        f"- **Average Latency:** {avg_latency:.0f} ms",
        f"- **Average Retries:** {avg_retries:.2f}",
        "",
        "## Accuracy by Difficulty"
    ]
    
    for diff in ["easy", "medium", "hard"]:
        if diff in diff_stats:
            stats = diff_stats[diff]
            acc = (stats["passed"] / stats["total"]) * 100
            report.append(f"- **{diff.capitalize()}:** {acc:.1f}% ({stats['passed']}/{stats['total']})")

    report.extend(["", "## Detailed Results", ""])
    
    table_data = []
    for r in results:
        status = "✅ Pass" if r.success else "❌ Fail"
        reason = r.failure_reason if not r.success else "-"
        table_data.append([r.test_id, r.difficulty, status, f"{r.latency_ms:.0f}ms", r.retries, reason])
        
    report.append(tabulate(
        table_data, 
        headers=["ID", "Difficulty", "Status", "Latency", "Retries", "Failure Reason"],
        tablefmt="pipe"
    ))
    
    report.extend(["", "## Failed Queries Analysis", ""])
    failures = [r for r in results if not r.success]
    if failures:
        for r in failures:
            report.append(f"### {r.test_id}: {r.question}")
            report.append(f"**Reason:** {r.failure_reason}")
            report.append(f"**Generated SQL:**\n```sql\n{r.sql}\n```\n")
    else:
        report.append("No failures! 🎉")

    report_str = "\n".join(report)
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_str)

    print(f"\nEvaluation Complete! Accuracy: {accuracy:.1f}%")
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    run_evaluation()
