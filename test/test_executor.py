"""
Tests for SQL execution and self-correction engine.
"""

import pytest
from app.services.executor import (
    validate_sql_syntax,
    sanitize_sql,
    build_correction_prompt,
)


# ── Syntax Validation Tests ──────────────────────────────────────────────────

def test_valid_select_passes():
    sql = "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '1 month'"
    is_valid, error = validate_sql_syntax(sql)
    assert is_valid is True
    assert error is None


def test_valid_cte_passes():
    sql = """
    WITH monthly_orders AS (
        SELECT user_id, COUNT(*) as order_count
        FROM orders
        GROUP BY user_id
    )
    SELECT * FROM monthly_orders WHERE order_count > 5
    """
    is_valid, error = validate_sql_syntax(sql)
    assert is_valid is True


def test_empty_sql_fails():
    is_valid, error = validate_sql_syntax("")
    assert is_valid is False
    assert error is not None


# ── SQL Sanitization Tests ───────────────────────────────────────────────────

def test_sanitize_strips_whitespace():
    sql = "  SELECT * FROM users  "
    assert sanitize_sql(sql) == "SELECT * FROM users"


def test_sanitize_strips_trailing_semicolon():
    sql = "SELECT * FROM users;"
    assert sanitize_sql(sql) == "SELECT * FROM users"


def test_sanitize_strips_markdown_fences():
    sql = "```sql\nSELECT * FROM users\n```"
    result = sanitize_sql(sql)
    assert "SELECT * FROM users" in result
    assert "```" not in result


def test_sanitize_strips_generic_fences():
    sql = "```\nSELECT * FROM users\n```"
    result = sanitize_sql(sql)
    assert "SELECT * FROM users" in result


# ── Self-Correction Prompt Tests ─────────────────────────────────────────────

def test_correction_prompt_includes_error():
    prompt = build_correction_prompt(
        original_prompt="Generate SQL for: how many users?",
        failed_sql="SELECT COUN(*) FROM users",
        error='ERROR: function coun(*) does not exist',
        dialect="postgresql",
    )
    assert "COUN(*) FROM users" in prompt
    assert "function coun(*) does not exist" in prompt
    assert "POSTGRESQL" in prompt


def test_correction_prompt_includes_dialect_hints():
    prompt = build_correction_prompt(
        original_prompt="Generate SQL",
        failed_sql="SELECT * FROM users WHERE date > '2024-01-01'",
        error="column date does not exist",
        dialect="postgresql",
    )
    assert "POSTGRESQL" in prompt
    assert "corrected" in prompt.lower()
