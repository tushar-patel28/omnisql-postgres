"""
scripts/build_demo_data.py
---------------------------
Pulls real predictions from the fine-tuned eval JSONL and produces
a TypeScript demo-data file for the frontend.

Selection strategy:
  - Force diversity: each schema gets one example per complexity tier
    where possible (simple -> moderate -> complex -> highly_complex)
  - Prefer exec_match=true within each tier
  - Output 12-16 examples that span the full difficulty range

Usage:
    python scripts/build_demo_data.py
"""

import json
import random
import re
from pathlib import Path
from collections import defaultdict

EVAL_FILE = "data/eval_omnisql-pg-finetuned-full_20260505_132926.jsonl"
OUTPUT_FILE = "frontend/src/lib/demo-data.ts"
SEED = 42

SCHEMA_LABELS = {
    "ecommerce":      {"label": "E-commerce",   "icon": "ShoppingBag", "color": "#6ea8ff"},
    "fintech":        {"label": "FinTech",      "icon": "Banknote",    "color": "#4ade80"},
    "healthcare":     {"label": "Healthcare",   "icon": "Stethoscope", "color": "#fb7185"},
    "hr_system":      {"label": "HR System",    "icon": "Users",       "color": "#fbbf24"},
    "saas_analytics": {"label": "SaaS",         "icon": "BarChart3",   "color": "#c084ff"},
}

# Per schema: which complexity tiers we want represented (in order of preference)
COMPLEXITY_TARGETS = ["simple", "moderate", "complex", "highly_complex"]


def load_eval(path: str):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pick_examples(rows: list[dict]) -> list[dict]:
    """For each schema, pick one example per complexity tier (where available)."""
    rng = random.Random(SEED)
    by_schema_complexity: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_schema_complexity[(r["schema_name"], r.get("complexity", "moderate"))].append(r)

    selected = []

    for schema in SCHEMA_LABELS:
        for complexity in COMPLEXITY_TARGETS:
            candidates = by_schema_complexity.get((schema, complexity), [])
            if not candidates:
                continue

            # Prefer exec_match=true, then highest BLEU, then shortest question (cleaner demo)
            candidates.sort(
                key=lambda r: (
                    not r.get("exec_match", False),
                    -float(r.get("bleu", 0)),
                    len(r.get("question", "")),
                )
            )
            selected.append(candidates[0])

    rng.shuffle(selected)
    return selected


# ── Smarter fake rows ────────────────────────────────────────────────────────

NAMES = ["Alice Chen", "Bob Williams", "Carol Singh", "Dave Park",
         "Eve Martinez", "Frank Liu", "Grace Patel", "Henry Brown"]


def fake_result_rows(generated_sql: str, schema_name: str, idx: int) -> list[dict]:
    """Synthesize plausible result rows that match the SQL shape."""
    sql = generated_sql.lower()

    # 1) Single COUNT scalar
    if re.search(r"select\s+count\s*\(\s*\*\s*\)", sql) and "group by" not in sql:
        return [{"count": 47 + idx * 13}]

    # 2) Single AVG / SUM scalar
    if re.search(r"select\s+(avg|sum)\s*\(", sql) and "group by" not in sql:
        if "avg" in sql:
            return [{"avg": round(2_847.39 + idx * 100, 2)}]
        return [{"total": round(184_392.55 + idx * 1000, 2)}]

    # 3) GROUP BY — categorical breakdown
    if "group by" in sql:
        groups = {
            "ecommerce":      ["electronics", "clothing", "books", "home"],
            "fintech":        ["checking", "savings", "credit", "investment"],
            "healthcare":     ["cardiology", "neurology", "pediatrics", "general"],
            "hr_system":      ["Engineering", "Sales", "Marketing", "HR"],
            "saas_analytics": ["pro", "free", "enterprise", "team"],
        }.get(schema_name, ["A", "B", "C", "D"])

        # Decide column names from SELECT clause shape
        if "count(" in sql:
            return [{"name": k, "count": (i + 2) * 7} for i, k in enumerate(groups)]
        if "avg(" in sql:
            return [
                {"name": k, "avg": round(1247.50 + i * 432.10, 2)}
                for i, k in enumerate(groups)
            ]
        if "sum(" in sql:
            return [
                {"name": k, "total": round(12_400 + i * 8_750, 2)}
                for i, k in enumerate(groups)
            ]
        return [{"name": k, "value": round(347.50 * (i + 2), 2)} for i, k in enumerate(groups)]

    # 4) Email lookup
    if "email" in sql:
        return [{"email": f"{n.lower().replace(' ', '.')}@example.com"}
                for n in NAMES[:4]]

    # 5) Name lookup
    if re.search(r"select\s+(distinct\s+)?\w*\.?name", sql):
        return [{"name": n} for n in NAMES[:5]]

    # 6) MRN (healthcare specific)
    if "mrn" in sql:
        return [{"mrn": f"MRN-{1000 + i * 137:04d}"} for i in range(5)]

    # 7) Title (HR specific — DISTINCT title)
    if "title" in sql and "distinct" in sql:
        return [{"title": t} for t in
                ["Engineer", "Senior Engineer", "Manager", "Director", "Analyst"]]

    # 8) ORDER BY ... LIMIT — top-N
    if "limit" in sql:
        return [
            {"id": i + 1, "name": NAMES[i], "score": round(95.3 - i * 4.2, 1)}
            for i in range(5)
        ]

    # 9) Generic SELECT * — return rows shaped per schema
    if "select *" in sql:
        per_schema = {
            "ecommerce":      [{"id": i + 1, "user_id": 100 + i, "total": round(125 * (i + 1), 2), "status": s}
                               for i, s in enumerate(["pending", "shipped", "delivered", "pending"])],
            "fintech":        [{"id": i + 1, "account_type": t, "amount": round(347.50 * (i + 2), 2), "category": c}
                               for i, (t, c) in enumerate([("checking", "food"), ("savings", "transport"),
                                                            ("checking", "food"), ("credit", "entertainment")])],
            "healthcare":     [{"id": i + 1, "patient_id": 200 + i, "scheduled_at": f"2024-{6+i:02d}-15", "status": s}
                               for i, s in enumerate(["scheduled", "completed", "cancelled", "scheduled"])],
            "hr_system":      [{"id": i + 1, "name": NAMES[i], "title": t, "salary": 65_000 + i * 8_000}
                               for i, t in enumerate(["Engineer", "Manager", "Analyst", "Director"])],
            "saas_analytics": [{"id": i + 1, "email": f"{NAMES[i].lower().replace(' ', '.')}@x.com", "role": r}
                               for i, r in enumerate(["owner", "member", "viewer", "owner"])],
        }
        return per_schema.get(schema_name, [{"id": i + 1} for i in range(4)])

    # 10) Fallback: scalar
    return [{"value": f"result_{i+1}"} for i in range(3)]


def to_ts_examples(examples: list[dict]) -> str:
    items = []
    for i, ex in enumerate(examples):
        question = ex["question"].replace('"', '\\"').replace("\n", " ")
        gen_sql = ex["generated_sql"].replace("`", "\\`")
        ref_sql = ex["reference_sql"].replace("`", "\\`")
        complexity = ex.get("complexity", "moderate")
        bleu = ex.get("bleu", 0.0)
        exec_match = ex.get("exec_match", False)
        schema_name = ex["schema_name"]
        rows = fake_result_rows(ex["generated_sql"], schema_name, i)

        items.append(
            f"""  {{
    id: "demo-{i+1:02d}",
    schema: "{schema_name}",
    complexity: "{complexity}",
    question: "{question}",
    generatedSql: `{gen_sql}`,
    referenceSql: `{ref_sql}`,
    bleu: {bleu},
    execMatch: {str(exec_match).lower()},
    latencyMs: {1200 + (i * 137) % 800},
    rows: {json.dumps(rows, ensure_ascii=False)},
  }}"""
        )
    return ",\n".join(items)


def main():
    eval_path = Path(EVAL_FILE)
    if not eval_path.exists():
        raise FileNotFoundError(f"Eval file not found: {EVAL_FILE}")

    rows = load_eval(EVAL_FILE)
    print(f"Loaded {len(rows)} eval rows")

    selected = pick_examples(rows)
    print(f"Selected {len(selected)} examples across {len({s['schema_name'] for s in selected})} schemas")

    # Print complexity distribution for verification
    from collections import Counter
    print("Complexity distribution:")
    for k, v in sorted(Counter(s["complexity"] for s in selected).items()):
        print(f"  {k}: {v}")

    schemas_block = ",\n".join(
        f'  {k}: {{ label: "{v["label"]}", icon: "{v["icon"]}", color: "{v["color"]}" }}'
        for k, v in SCHEMA_LABELS.items()
    )

    examples_block = to_ts_examples(selected)

    ts = f"""// Auto-generated by scripts/build_demo_data.py
// Source: {EVAL_FILE}
// DO NOT EDIT BY HAND — regenerate via `python scripts/build_demo_data.py`

export type SchemaName =
  | "ecommerce"
  | "fintech"
  | "healthcare"
  | "hr_system"
  | "saas_analytics";

export type Complexity = "simple" | "moderate" | "complex" | "highly_complex";

export interface DemoExample {{
  id: string;
  schema: SchemaName;
  complexity: Complexity;
  question: string;
  generatedSql: string;
  referenceSql: string;
  bleu: number;
  execMatch: boolean;
  latencyMs: number;
  rows: Record<string, unknown>[];
}}

export interface SchemaMeta {{
  label: string;
  icon: string;
  color: string;
}}

export const SCHEMAS: Record<SchemaName, SchemaMeta> = {{
{schemas_block},
}};

export const DEMO_EXAMPLES: DemoExample[] = [
{examples_block},
];

// Aggregated headline metrics (from real eval, see ~/omnisql-results/)
export const EVAL_METRICS = {{
  finetuned: {{ executionAccuracy: 0.46, validityRate: 0.94, bleu: 0.585 }},
  baseline:  {{ executionAccuracy: 0.07, validityRate: 0.15, bleu: 0.204 }},
  testSize: 200,
}};
"""

    out_path = Path(OUTPUT_FILE)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ts)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()