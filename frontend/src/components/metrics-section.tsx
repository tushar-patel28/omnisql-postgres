"use client";

import {
  EVAL_METRICS,
  SCHEMAS,
  COMPLEXITY_LABELS,
  type SchemaName,
  type Complexity,
} from "@/lib/demo-data";

const SCHEMA_ORDER: SchemaName[] = [
  "ecommerce",
  "fintech",
  "healthcare",
  "hr_system",
  "saas_analytics",
];

const COMPLEXITY_ORDER: Complexity[] = [
  "simple",
  "moderate",
  "complex",
  "highly_complex",
];

export function MetricsSection() {
  const ft = EVAL_METRICS.finetuned;
  const bl = EVAL_METRICS.baseline;
  const lift =
    (ft.overall.executionAccuracy / Math.max(bl.overall.executionAccuracy, 1e-9));

  return (
    <div className="space-y-12">
      {/* ── Overall comparison ───────────────────────────────────── */}
      <div className="glass rounded-2xl p-8 md:p-12">
        <div className="grid md:grid-cols-[1.1fr_2fr] gap-10 items-center">
          {/* Left: big number */}
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-3">
              Execution accuracy
            </div>
            <div className="font-display text-7xl md:text-8xl leading-none tracking-tight">
              <span className="gradient-text">
                {pct(ft.overall.executionAccuracy)}
              </span>
            </div>
            <div className="mt-4 flex items-baseline gap-2 text-sm font-mono">
              <span className="text-chart-3">
                {lift.toFixed(1)}× over baseline
              </span>
              <span className="text-muted-foreground/50">·</span>
              <span className="text-muted-foreground">
                from {pct(bl.overall.executionAccuracy)}
              </span>
            </div>
          </div>

          {/* Right: bar comparison */}
          <div className="space-y-4">
            <BarRow
              label="OmniSQL-Pg (fine-tuned)"
              value={ft.overall.executionAccuracy}
              color="var(--primary)"
              isPrimary
            />
            <BarRow
              label="OmniSQL-7B (baseline)"
              value={bl.overall.executionAccuracy}
              color="var(--muted-foreground)"
            />
            <div className="pt-2 grid grid-cols-3 gap-4 text-xs font-mono border-t border-border/40 pt-4">
              <Stat
                label="Validity"
                ftValue={pct(ft.overall.validityRate)}
                blValue={pct(bl.overall.validityRate)}
              />
              <Stat
                label="BLEU"
                ftValue={ft.overall.bleu.toFixed(2)}
                blValue={bl.overall.bleu.toFixed(2)}
              />
              <Stat
                label="Test set"
                ftValue={`${EVAL_METRICS.testSize} pairs`}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Per-schema breakdown ────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-6">
          <h3 className="font-display text-2xl">By schema</h3>
          <div className="flex items-center gap-4 text-xs font-mono">
            <Legend color="var(--primary)" label="Fine-tuned" />
            <Legend color="var(--muted-foreground)" label="Baseline" />
          </div>
        </div>

        <div className="glass rounded-2xl p-6 md:p-8 space-y-5">
          {SCHEMA_ORDER.map((s) => {
            const meta = SCHEMAS[s];
            const ftVal = ft.bySchema[s]?.executionAccuracy ?? 0;
            const blVal = bl.bySchema[s]?.executionAccuracy ?? 0;
            return (
              <PairedBars
                key={s}
                label={meta.label}
                accentColor={meta.color}
                ftValue={ftVal}
                blValue={blVal}
              />
            );
          })}
        </div>
      </div>

      {/* ── Per-complexity breakdown ────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-6">
          <h3 className="font-display text-2xl">By complexity</h3>
          <div className="flex items-center gap-4 text-xs font-mono">
            <Legend color="var(--accent)" label="Fine-tuned" />
            <Legend color="var(--muted-foreground)" label="Baseline" />
          </div>
        </div>

        <div className="glass rounded-2xl p-6 md:p-8 space-y-5">
          {COMPLEXITY_ORDER.map((c) => {
            const ftVal = ft.byComplexity[c]?.executionAccuracy ?? 0;
            const blVal = bl.byComplexity[c]?.executionAccuracy ?? 0;
            return (
              <PairedBars
                key={c}
                label={COMPLEXITY_LABELS[c]}
                accentColor="var(--accent)"
                ftValue={ftVal}
                blValue={blVal}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Bits ────────────────────────────────────────────────────── */

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function BarRow({
  label,
  value,
  color,
  isPrimary,
}: {
  label: string;
  value: number;
  color: string;
  isPrimary?: boolean;
}) {
  const widthPct = Math.max(value * 100, 2);
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2 text-sm">
        <span className="font-mono text-muted-foreground">{label}</span>
        <span
          className={`font-mono ${
            isPrimary ? "text-foreground font-medium" : "text-muted-foreground"
          }`}
        >
          {pct(value)}
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-muted/40 overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-1000"
          style={{
            width: `${widthPct}%`,
            background: isPrimary
              ? `linear-gradient(90deg, ${color}, var(--accent))`
              : color,
            boxShadow: isPrimary ? `0 0 16px -2px ${color}` : undefined,
            opacity: isPrimary ? 1 : 0.4,
          }}
        />
      </div>
    </div>
  );
}

function PairedBars({
  label,
  accentColor,
  ftValue,
  blValue,
}: {
  label: string;
  accentColor: string;
  ftValue: number;
  blValue: number;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr_60px] md:grid-cols-[180px_1fr_70px] items-center gap-4">
      <span className="font-mono text-sm text-muted-foreground truncate">
        {label}
      </span>
      <div className="space-y-1.5">
        <div className="relative h-2 rounded-full bg-muted/40 overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-1000"
            style={{
              width: `${Math.max(ftValue * 100, 1)}%`,
              background: `linear-gradient(90deg, ${accentColor}, var(--primary))`,
              boxShadow: `0 0 12px -2px ${accentColor}`,
            }}
          />
        </div>
        <div className="relative h-2 rounded-full bg-muted/40 overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-1000"
            style={{
              width: `${Math.max(blValue * 100, 1)}%`,
              background: "var(--muted-foreground)",
              opacity: 0.4,
            }}
          />
        </div>
      </div>
      <div className="font-mono text-xs text-right">
        <div className="text-foreground">{pct(ftValue)}</div>
        <div className="text-muted-foreground/60">{pct(blValue)}</div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-2 text-muted-foreground">
      <span
        className="w-2.5 h-2.5 rounded-full"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}

function Stat({
  label,
  ftValue,
  blValue,
}: {
  label: string;
  ftValue: string;
  blValue?: string;
}) {
  return (
    <div>
      <div className="text-muted-foreground/60 uppercase tracking-widest text-[10px] mb-1">
        {label}
      </div>
      <div className="text-foreground">{ftValue}</div>
      {blValue && (
        <div className="text-muted-foreground/50 text-[11px]">
          base {blValue}
        </div>
      )}
    </div>
  );
}