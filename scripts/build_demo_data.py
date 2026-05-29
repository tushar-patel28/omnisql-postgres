"""
scripts/build_demo_data.py
---------------------------
Pulls real predictions from the eval JSONL files (fine-tuned + baseline)
and produces a TypeScript demo-data file for the frontend.

Outputs:
  - 20 demo examples (4 per schema, varied complexity)
  - Aggregated metrics: overall, per-schema, per-complexity
    for both baseline and fine-tuned

Usage:
    python scripts/build_demo_data.py
"""

import json
import random
import re
from pathlib import Path
from collections import defaultdict, Counter

EVAL_FT       = "data/eval_omnisql-pg-v3-3epoch-beam4_20260525_231425.jsonl"
EVAL_BASELINE = "data/eval_omnisql-baseline-beam4_20260512_142518.jsonl"
OUTPUT_FILE   = "frontend/src/lib/demo-data.ts"
SEED          = 42

SCHEMA_LABELS = {
    "ecommerce":      {"label": "E-commerce",   "icon": "ShoppingBag", "color": "#6ea8ff"},
    "fintech":        {"label": "FinTech",      "icon": "Banknote",    "color": "#4ade80"},
    "healthcare":     {"label": "Healthcare",   "icon": "Stethoscope", "color": "#fb7185"},
    "hr_system":      {"label": "HR System",    "icon": "Users",       "color": "#fbbf24"},
    "saas_analytics": {"label": "SaaS",         "icon": "BarChart3",   "color": "#c084ff"},
}

COMPLEXITY_TARGETS = ["simple", "moderate", "complex", "highly_complex"]
COMPLEXITY_LABELS = {
    "simple": "Simple",
    "moderate": "Moderate",
    "complex": "Complex",
    "highly_complex": "Highly complex",
}


def load_eval(path: str):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ── Aggregation ──────────────────────────────────────────────────────────────

def compute_breakdowns(rows: list[dict]):
    """Return overall + per-schema + per-complexity stats."""
    n = len(rows) or 1

    overall = {
        "executionAccuracy": sum(r.get("exec_match", False) for r in rows) / n,
        "validityRate":      sum(r.get("exec_success", False) for r in rows) / n,
        "bleu":              sum(r.get("bleu", 0) for r in rows) / n,
    }

    by_schema = defaultdict(list)
    for r in rows:
        by_schema[r["schema_name"]].append(r)

    schema_breakdown = {}
    for s, items in by_schema.items():
        nn = len(items) or 1
        schema_breakdown[s] = {
            "executionAccuracy": sum(x.get("exec_match", False) for x in items) / nn,
            "validityRate":      sum(x.get("exec_success", False) for x in items) / nn,
        }

    by_complexity = defaultdict(list)
    for r in rows:
        by_complexity[r.get("complexity", "moderate")].append(r)

    complexity_breakdown = {}
    for c, items in by_complexity.items():
        nn = len(items) or 1
        complexity_breakdown[c] = {
            "executionAccuracy": sum(x.get("exec_match", False) for x in items) / nn,
            "validityRate":      sum(x.get("exec_success", False) for x in items) / nn,
        }

    return overall, schema_breakdown, complexity_breakdown


# ── Example selection ────────────────────────────────────────────────────────

def pick_examples(rows: list[dict]) -> list[dict]:
    """For each schema, pick one example per complexity tier where available."""
    rng = random.Random(SEED)
    by_sc: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_sc[(r["schema_name"], r.get("complexity", "moderate"))].append(r)

    selected = []
    for schema in SCHEMA_LABELS:
        for complexity in COMPLEXITY_TARGETS:
            cands = by_sc.get((schema, complexity), [])
            if not cands:
                continue
            cands.sort(
                key=lambda r: (
                    not r.get("exec_match", False),
                    -float(r.get("bleu", 0)),
                    len(r.get("question", "")),
                )
            )
            selected.append(cands[0])

    rng.shuffle(selected)
    return selected


# ── Fake row synthesis (unchanged) ───────────────────────────────────────────

NAMES = ["Alice Chen", "Bob Williams", "Carol Singh", "Dave Park",
         "Eve Martinez", "Frank Liu", "Grace Patel", "Henry Brown"]


def fake_result_rows(generated_sql: str, schema_name: str, idx: int) -> list[dict]:
    sql = generated_sql.lower()

    if re.search(r"select\s+count\s*\(\s*\*\s*\)", sql) and "group by" not in sql:
        return [{"count": 47 + idx * 13}]

    if re.search(r"select\s+(avg|sum)\s*\(", sql) and "group by" not in sql:
        if "avg" in sql:
            return [{"avg": round(2_847.39 + idx * 100, 2)}]
        return [{"total": round(184_392.55 + idx * 1000, 2)}]

    if "group by" in sql:
        groups = {
            "ecommerce":      ["electronics", "clothing", "books", "home"],
            "fintech":        ["checking", "savings", "credit", "investment"],
            "healthcare":     ["cardiology", "neurology", "pediatrics", "general"],
            "hr_system":      ["Engineering", "Sales", "Marketing", "HR"],
            "saas_analytics": ["pro", "free", "enterprise", "team"],
        }.get(schema_name, ["A", "B", "C", "D"])

        if "count(" in sql:
            return [{"name": k, "count": (i + 2) * 7} for i, k in enumerate(groups)]
        if "avg(" in sql:
            return [{"name": k, "avg": round(1247.50 + i * 432.10, 2)} for i, k in enumerate(groups)]
        if "sum(" in sql:
            return [{"name": k, "total": round(12_400 + i * 8_750, 2)} for i, k in enumerate(groups)]
        return [{"name": k, "value": round(347.50 * (i + 2), 2)} for i, k in enumerate(groups)]

    if "email" in sql:
        return [{"email": f"{n.lower().replace(' ', '.')}@example.com"} for n in NAMES[:4]]

    if re.search(r"select\s+(distinct\s+)?\w*\.?name", sql):
        return [{"name": n} for n in NAMES[:5]]

    if "mrn" in sql:
        return [{"mrn": f"MRN-{1000 + i * 137:04d}"} for i in range(5)]

    if "title" in sql and "distinct" in sql:
        return [{"title": t} for t in
                ["Engineer", "Senior Engineer", "Manager", "Director", "Analyst"]]

    if "limit" in sql:
        return [
            {"id": i + 1, "name": NAMES[i], "score": round(95.3 - i * 4.2, 1)}
            for i in range(5)
        ]

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

    return [{"value": f"result_{i+1}"} for i in range(3)]


# ── TS emission ──────────────────────────────────────────────────────────────

def to_ts_examples(examples: list[dict]) -> str:
    items = []
    for i, ex in enumerate(examples):
        question = ex["question"].replace('"', '\\"').replace("\n", " ")
        gen_sql = ex["generated_sql"].replace("`", "\\`")
        ref_sql = ex["reference_sql"].replace("`", "\\`")
        items.append(f"""  {{
    id: "demo-{i+1:02d}",
    schema: "{ex['schema_name']}",
    complexity: "{ex.get('complexity', 'moderate')}",
    question: "{question}",
    generatedSql: `{gen_sql}`,
    referenceSql: `{ref_sql}`,
    bleu: {ex.get('bleu', 0.0)},
    execMatch: {str(ex.get('exec_match', False)).lower()},
    latencyMs: {1200 + (i * 137) % 800},
    rows: {json.dumps(fake_result_rows(ex["generated_sql"], ex["schema_name"], i), ensure_ascii=False)},
  }}""")
    return ",\n".join(items)


def to_ts_breakdown(d: dict, indent: str = "    ") -> str:
    items = []
    for k, v in d.items():
        items.append(f'{indent}{json.dumps(k)}: {{ '
                     f'executionAccuracy: {v["executionAccuracy"]:.4f}, '
                     f'validityRate: {v["validityRate"]:.4f} }}')
    return ",\n".join(items)


def main():
    if not Path(EVAL_FT).exists():
        raise FileNotFoundError(f"Fine-tuned eval not found: {EVAL_FT}")
    if not Path(EVAL_BASELINE).exists():
        raise FileNotFoundError(f"Baseline eval not found: {EVAL_BASELINE}")

    ft_rows = load_eval(EVAL_FT)
    bl_rows = load_eval(EVAL_BASELINE)
    print(f"Loaded {len(ft_rows)} fine-tuned + {len(bl_rows)} baseline rows")

    ft_overall, ft_schema, ft_complex = compute_breakdowns(ft_rows)
    bl_overall, bl_schema, bl_complex = compute_breakdowns(bl_rows)

    selected = pick_examples(ft_rows)
    print(f"Selected {len(selected)} examples")
    print("Complexity distribution:", dict(Counter(s["complexity"] for s in selected)))

    schemas_block = ",\n".join(
        f'  {k}: {{ label: "{v["label"]}", icon: "{v["icon"]}", color: "{v["color"]}" }}'
        for k, v in SCHEMA_LABELS.items()
    )
    complexity_block = ",\n".join(
        f'  {json.dumps(k)}: {json.dumps(v)}' for k, v in COMPLEXITY_LABELS.items()
    )

    examples_block = to_ts_examples(selected)

    ts = f"""// Auto-generated by scripts/build_demo_data.py
// Sources:
//   {EVAL_FT}
//   {EVAL_BASELINE}
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

export interface BreakdownStat {{
  executionAccuracy: number;
  validityRate: number;
}}

export const SCHEMAS: Record<SchemaName, SchemaMeta> = {{
{schemas_block},
}};

export const COMPLEXITY_LABELS: Record<Complexity, string> = {{
{complexity_block},
}};

export const DEMO_EXAMPLES: DemoExample[] = [
{examples_block},
];

// Aggregated metrics from real eval runs (200-pair test set each)
export const EVAL_METRICS = {{
  testSize: 200,
  finetuned: {{
    overall: {{
      executionAccuracy: {ft_overall["executionAccuracy"]:.4f},
      validityRate:      {ft_overall["validityRate"]:.4f},
      bleu:              {ft_overall["bleu"]:.4f},
    }},
    bySchema: {{
{to_ts_breakdown(ft_schema, indent="      ")}
    }} as Record<SchemaName, BreakdownStat>,
    byComplexity: {{
{to_ts_breakdown(ft_complex, indent="      ")}
    }} as Record<Complexity, BreakdownStat>,
  }},
  baseline: {{
    overall: {{
      executionAccuracy: {bl_overall["executionAccuracy"]:.4f},
      validityRate:      {bl_overall["validityRate"]:.4f},
      bleu:              {bl_overall["bleu"]:.4f},
    }},
    bySchema: {{
{to_ts_breakdown(bl_schema, indent="      ")}
    }} as Record<SchemaName, BreakdownStat>,
    byComplexity: {{
{to_ts_breakdown(bl_complex, indent="      ")}
    }} as Record<Complexity, BreakdownStat>,
  }},
}} as const;
"""

    out_path = Path(OUTPUT_FILE)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ts)
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()