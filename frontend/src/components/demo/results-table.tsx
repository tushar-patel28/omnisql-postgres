"use client";

import { Database, Zap, CheckCircle2, AlertCircle } from "lucide-react";
import type { DemoExample } from "@/lib/demo-data";

interface ResultsTableProps {
  example: DemoExample;
}

export function ResultsTable({ example }: ResultsTableProps) {
  const rows = example.rows;
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
    <div className="glass rounded-xl overflow-hidden">
      {/* Header bar with metrics */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-foreground/[0.02]">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
          <Database className="w-3.5 h-3.5 text-chart-3" />
          <span>query_results</span>
          <span className="text-muted-foreground/40">·</span>
          <span className="text-muted-foreground/60">{rows.length} rows</span>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono">
          <Metric
            icon={<Zap className="w-3 h-3" />}
            label={`${example.latencyMs}ms`}
            tone="muted"
          />
          <Metric
            icon={
              example.execMatch ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : (
                <AlertCircle className="w-3 h-3" />
              )
            }
            label={example.execMatch ? "exec match" : "diff"}
            tone={example.execMatch ? "success" : "warn"}
          />
          <Metric label={`bleu ${example.bleu.toFixed(2)}`} tone="muted" />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              {columns.map((col) => (
                <th
                  key={col}
                  className="
                    text-left px-4 py-2.5
                    font-mono text-[11px] uppercase tracking-widest
                    text-muted-foreground
                  "
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="
                  border-b border-border/20 last:border-0
                  hover:bg-foreground/[0.02]
                  transition-colors
                "
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-2.5 font-mono text-foreground/90"
                  >
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────────────── */

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    // Format larger numbers with separators
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

interface MetricProps {
  icon?: React.ReactNode;
  label: string;
  tone: "success" | "warn" | "muted";
}

function Metric({ icon, label, tone }: MetricProps) {
  const colors = {
    success: "text-chart-3",
    warn: "text-chart-4",
    muted: "text-muted-foreground",
  };
  return (
    <span className={`flex items-center gap-1 ${colors[tone]}`}>
      {icon}
      {label}
    </span>
  );
}