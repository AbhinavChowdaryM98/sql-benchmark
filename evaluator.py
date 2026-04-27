"""
Execution-based evaluation with value overlap / partial match.

Match logic:
  - Execute gold SQL and predicted SQL against the same SQLite DB.
  - Flatten both result sets to sets of values (cast to str, stripped).
  - Compute precision, recall, F1 over value sets.
  - execution_match = True if F1 >= MATCH_THRESHOLD (default 1.0 = exact value overlap).

You can lower MATCH_THRESHOLD (e.g. 0.8) for partial credit.
"""
import sqlite3
import re
from typing import Any

MATCH_THRESHOLD = 1.0  # F1 threshold for execution_match=True


def _execute(conn: sqlite3.Connection, sql: str) -> tuple[list, str | None]:
    """Run SQL, return (rows, error). rows=[] on error."""
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        return rows, None
    except Exception as e:
        return [], str(e)


def _flatten(rows: list[tuple]) -> set[str]:
    """Flatten result rows to a set of string values."""
    values = set()
    for row in rows:
        for cell in row:
            if cell is not None:
                values.add(str(cell).strip().lower())
    return values


def _f1(gold_vals: set[str], pred_vals: set[str]) -> float:
    if not gold_vals and not pred_vals:
        return 1.0
    if not gold_vals or not pred_vals:
        return 0.0
    intersection = gold_vals & pred_vals
    precision = len(intersection) / len(pred_vals)
    recall = len(intersection) / len(gold_vals)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _row_count_match(gold_rows: list, pred_rows: list) -> bool:
    return len(gold_rows) == len(pred_rows)


def clean_sql(sql: str) -> str:
    """Strip markdown fences and trailing semicolons."""
    sql = re.sub(r"```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    return sql.strip().rstrip(";")


def evaluate(db_path: str, gold_sql: str, predicted_sql: str) -> dict:
    """
    Returns dict with:
      execution_match, f1, precision, recall,
      gold_row_count, pred_row_count,
      gold_error, pred_error
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    gold_sql = clean_sql(gold_sql)
    predicted_sql = clean_sql(predicted_sql)

    gold_rows, gold_err = _execute(conn, gold_sql)
    pred_rows, pred_err = _execute(conn, predicted_sql)
    conn.close()

    if pred_err:
        return {
            "execution_match": False,
            "f1": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "gold_row_count": len(gold_rows),
            "pred_row_count": 0,
            "gold_error": gold_err,
            "pred_error": pred_err,
        }

    gold_vals = _flatten(gold_rows)
    pred_vals = _flatten(pred_rows)

    f1 = _f1(gold_vals, pred_vals)
    intersection = gold_vals & pred_vals
    precision = len(intersection) / len(pred_vals) if pred_vals else 0.0
    recall = len(intersection) / len(gold_vals) if gold_vals else 0.0

    return {
        "execution_match": f1 >= MATCH_THRESHOLD,
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "gold_row_count": len(gold_rows),
        "pred_row_count": len(pred_rows),
        "gold_error": gold_err,
        "pred_error": pred_err,
    }
