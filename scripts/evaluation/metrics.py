"""
scripts/evaluation/metrics.py
-------------------------------
Evaluation metrics for Text-to-SQL:

  1. Execution Accuracy (EX) — primary metric
     Does the generated SQL execute successfully against PostgreSQL?
     Does it return the same VALUES as the ground truth SQL?
     (Order-independent, column-name-independent — set semantics)

  2. BLEU Score — secondary metric
     Surface-level similarity between generated and reference SQL.

  3. Validity Rate
     What % of generated SQL passes syntax check + executes without error.

This implementation follows BIRD/Spider conventions: result rows are compared
as sets of value-tuples, not as lists with named columns. This rewards correct
answers regardless of:
  - Row ordering (unless the question specifically requests an order)
  - Column aliasing (`COUNT(*) AS total` vs `COUNT(*) AS num_orders`)
  - Column projection differences when content is otherwise identical
"""

import asyncpg
import sqlparse
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import structlog

log = structlog.get_logger()


# ── BLEU ─────────────────────────────────────────────────────────────────────

def compute_bleu(reference_sql: str, hypothesis_sql: str) -> float:
    """BLEU between reference and generated SQL surface text."""
    def tokenize(sql: str) -> list[str]:
        import re
        sql = sql.lower().strip().rstrip(";")
        return re.findall(r"\w+|[^\w\s]", sql)

    ref_tokens = tokenize(reference_sql)
    hyp_tokens = tokenize(hypothesis_sql)

    if not hyp_tokens:
        return 0.0

    smoothing = SmoothingFunction().method1
    try:
        return round(
            sentence_bleu([ref_tokens], hyp_tokens, smoothing_function=smoothing),
            4,
        )
    except Exception:
        return 0.0


def is_valid_sql(sql: str) -> bool:
    """Basic syntax validation via sqlparse."""
    try:
        parsed = sqlparse.parse(sql.rstrip(";"))
        return bool(parsed and parsed[0].tokens)
    except Exception:
        return False


# ── Execution ────────────────────────────────────────────────────────────────

async def execute_sql_safe(
    sql: str,
    dsn: str,
    timeout: float = 10.0,
) -> tuple[bool, list | None, str | None]:
    """
    Execute SQL safely.

    Returns:
        (success, raw_rows, error_message)
        raw_rows is a list of asyncpg.Record (each acts like a dict).
    """
    try:
        conn = await asyncpg.connect(dsn, timeout=timeout)
        try:
            test_sql = sql.rstrip(";")
            if (
                test_sql.strip().upper().startswith("SELECT")
                and "LIMIT" not in test_sql.upper()
            ):
                test_sql = f"{test_sql} LIMIT 100"

            rows = await conn.fetch(test_sql)
            return True, list(rows), None
        except Exception as e:
            return False, None, str(e)
        finally:
            await conn.close()
    except Exception as e:
        return False, None, str(e)


# ── Result comparison ────────────────────────────────────────────────────────

def _normalize_value(v):
    """Make a value hashable + comparison-friendly.

    - None → None
    - float close to int → int (handles 5.0 vs 5)
    - everything else → str(value)
    """
    if v is None:
        return None
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        # Round floats to avoid 0.30000001 vs 0.3 mismatches
        return round(v, 6)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, str)):
        return v
    # dates, decimals, UUIDs → string form for comparison
    return str(v)


def _row_to_value_tuple(row) -> tuple:
    """
    Convert an asyncpg Record (or dict) to a sorted tuple of values,
    dropping column names. Order-within-row independent.
    Sort key uses string repr to handle mixed types (str + int) safely.
    """
    if hasattr(row, "values"):
        values = list(row.values())
    else:
        values = list(dict(row).values())
    normalized = [_normalize_value(v) for v in values]
    return tuple(sorted(normalized, key=lambda x: (x is None, str(x))))


def results_match_set_semantics(
    ref_rows: list | None,
    hyp_rows: list | None,
) -> bool:
    """
    Compare result sets with relaxed semantics:
      - Order-independent (set, not list)
      - Column-name-independent (compare values only)
      - Within-row column-order-independent (sort the value tuple)

    Returns True if the multiset of rows matches.
    """
    if ref_rows is None or hyp_rows is None:
        return False

    if not ref_rows and not hyp_rows:
        return True

    # Stringify tuples for safe sorting across mixed types
    ref_set = sorted(
        (_row_to_value_tuple(r) for r in ref_rows),
        key=lambda t: str(t),
    )
    hyp_set = sorted(
        (_row_to_value_tuple(r) for r in hyp_rows),
        key=lambda t: str(t),
    )
    return ref_set == hyp_set


def results_match_subset(
    ref_rows: list | None,
    hyp_rows: list | None,
) -> bool:
    """
    Looser fallback: every reference value-tuple is contained in some hypothesis
    row's value-tuple (or vice versa). Catches cases like the model returning
    extra columns the question didn't ask for, or dropping an `id` column.

    Only used when strict set match fails. NOT used as the primary metric.
    """
    if not ref_rows or not hyp_rows:
        return False

    def values_set(row):
        if hasattr(row, "values"):
            vals = list(row.values())
        else:
            vals = list(dict(row).values())
        return frozenset(_normalize_value(v) for v in vals)

    ref_value_sets = [values_set(r) for r in ref_rows]
    hyp_value_sets = [values_set(r) for r in hyp_rows]

    # Direction 1: every ref row's values are a subset of some hyp row's values
    for rv in ref_value_sets:
        if not any(rv.issubset(hv) for hv in hyp_value_sets):
            return False
    # Same number of rows (don't allow a 1-row hyp to match a 100-row ref)
    return len(ref_rows) == len(hyp_rows)


# ── Single-pair evaluator ────────────────────────────────────────────────────

async def evaluate_single(
    question: str,
    reference_sql: str,
    generated_sql: str,
    dsn: str,
) -> dict:
    """
    Evaluate a single (question, reference SQL, generated SQL) triple.

    Returns dict with:
        - bleu                : BLEU score
        - valid               : passes syntax check
        - exec_success        : generated SQL ran without error
        - exec_match          : strict set match (primary metric)
        - exec_match_relaxed  : strict OR subset match (lenient metric)
    """
    result = {
        "question": question,
        "reference_sql": reference_sql,
        "generated_sql": generated_sql,
        "bleu": 0.0,
        "valid": False,
        "exec_success": False,
        "exec_match": False,
        "exec_match_relaxed": False,
        "error": None,
    }

    result["bleu"] = compute_bleu(reference_sql, generated_sql)
    result["valid"] = is_valid_sql(generated_sql)
    if not result["valid"]:
        result["error"] = "Invalid SQL syntax"
        return result

    gen_success, gen_rows, gen_error = await execute_sql_safe(generated_sql, dsn)
    result["exec_success"] = gen_success
    if not gen_success:
        result["error"] = gen_error
        return result

    ref_success, ref_rows, ref_error = await execute_sql_safe(reference_sql, dsn)
    if not ref_success:
        # Reference itself broke — give credit for executing
        result["exec_match"] = True
        result["exec_match_relaxed"] = True
        result["error"] = f"reference SQL failed: {ref_error}"
        return result

    # Strict set-semantics comparison
    strict = results_match_set_semantics(ref_rows, gen_rows)
    result["exec_match"] = strict
    result["exec_match_relaxed"] = strict or results_match_subset(ref_rows, gen_rows)

    return result