"""
scripts/synthesis/inspect_dataset.py
--------------------------------------
Inspect and validate the generated PostgreSQL training dataset.
Shows statistics, samples, and quality metrics.

Usage:
    python scripts/synthesis/inspect_dataset.py --input data/synthetic/pg_train.jsonl
"""

import json
import argparse
import re
from pathlib import Path
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def load_dataset(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def detect_pg_features(sql: str) -> list[str]:
    """Detect which PostgreSQL-specific features are used in a SQL query."""
    features = []
    sql_upper = sql.upper()

    checks = {
        "DATE_TRUNC": "DATE_TRUNC",
        "EXTRACT": "EXTRACT(",
        "ILIKE": " ILIKE ",
        "Window Function": " OVER (",
        "CTE": " WITH ",
        "JSONB": "->",
        "ARRAY_AGG": "ARRAY_AGG",
        "STRING_AGG": "STRING_AGG",
        "COALESCE": "COALESCE",
        "NULLIF": "NULLIF",
        "FILTER": ") FILTER (",
        "PERCENTILE": "PERCENTILE_",
        "INTERVAL": " INTERVAL ",
    }

    for feature, pattern in checks.items():
        if pattern in sql_upper:
            features.append(feature)

    return features


def main(input_path: str):
    pairs = load_dataset(input_path)

    console.print(f"\n[bold green]Dataset: {input_path}[/bold green]")
    console.print(f"Total pairs: [bold]{len(pairs)}[/bold]\n")

    # ── Complexity distribution ──────────────────────────────────────────────
    complexity_counts = Counter(p["complexity"] for p in pairs)
    table = Table(title="Complexity Distribution")
    table.add_column("Complexity", style="cyan")
    table.add_column("Count", style="green")
    table.add_column("Percentage", style="yellow")
    for complexity, count in sorted(complexity_counts.items()):
        table.add_row(complexity, str(count), f"{count/len(pairs)*100:.1f}%")
    console.print(table)

    # ── Schema distribution ──────────────────────────────────────────────────
    schema_counts = Counter(p["schema_name"] for p in pairs)
    table2 = Table(title="Schema Distribution")
    table2.add_column("Schema", style="cyan")
    table2.add_column("Count", style="green")
    for schema, count in sorted(schema_counts.items()):
        table2.add_row(schema, str(count))
    console.print(table2)

    # ── PostgreSQL feature coverage ──────────────────────────────────────────
    all_features = []
    for p in pairs:
        all_features.extend(detect_pg_features(p["sql"]))
    feature_counts = Counter(all_features)

    table3 = Table(title="PostgreSQL Feature Coverage")
    table3.add_column("Feature", style="cyan")
    table3.add_column("Count", style="green")
    table3.add_column("Coverage %", style="yellow")
    for feature, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
        table3.add_row(feature, str(count), f"{count/len(pairs)*100:.1f}%")
    console.print(table3)

    # ── Sample pairs ─────────────────────────────────────────────────────────
    console.print("\n[bold]Sample pairs (one per complexity):[/bold]\n")
    shown = set()
    for pair in pairs:
        if pair["complexity"] not in shown:
            shown.add(pair["complexity"])
            console.print(Panel(
                f"[yellow]Question:[/yellow] {pair['question']}\n\n"
                f"[cyan]SQL:[/cyan]\n{pair['sql']}\n\n"
                f"[dim]Schema: {pair['schema_name']} | Complexity: {pair['complexity']}[/dim]",
                title=f"[bold]{pair['complexity'].upper()}[/bold]",
            ))
        if len(shown) == 4:
            break

    # ── Quality checks ───────────────────────────────────────────────────────
    issues = []
    for i, pair in enumerate(pairs):
        if not pair.get("sql"):
            issues.append(f"Row {i}: missing SQL")
        if not pair.get("question"):
            issues.append(f"Row {i}: missing question")
        if "strftime" in pair.get("sql", "").lower():
            issues.append(f"Row {i}: SQLite syntax detected (strftime)")

    if issues:
        console.print(f"\n[red]⚠️  {len(issues)} quality issues found:[/red]")
        for issue in issues[:10]:
            console.print(f"  - {issue}")
    else:
        console.print("\n[green]✅ No quality issues found[/green]")

    console.print(f"\n[bold]Dataset ready for fine-tuning: {input_path}[/bold]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/synthetic/pg_train.jsonl")
    args = parser.parse_args()
    main(args.input)