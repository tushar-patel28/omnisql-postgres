import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { SectionLabel } from "@/components/section-label";

export default function Home() {
  return (
    <>
      <SiteHeader />

      <main>
        {/* ── Hero ───────────────────────────────────────────────────── */}
        <section className="max-w-7xl mx-auto px-6 pt-24 pb-32">
          <div className="max-w-3xl">
            <SectionLabel>Phase 5 · Live</SectionLabel>

            <h1 className="font-display text-5xl md:text-7xl mt-6 leading-[1.05] tracking-tight">
              Natural language to{" "}
              <span className="gradient-text">PostgreSQL</span>,
              <br />
              fine-tuned for production.
            </h1>

            <p className="mt-8 text-lg text-muted-foreground leading-relaxed max-w-2xl">
              An MLOps research project extending OmniSQL-7B (VLDB&apos;25 SOTA)
              to PostgreSQL via QLoRA fine-tuning.{" "}
              <span className="text-foreground">6.6× improvement</span> in
              execution accuracy over the base model on a 200-pair test set.
            </p>

            <div className="mt-12 flex flex-wrap gap-3 font-mono text-xs">
              <Stat label="Execution accuracy" value="46.0%" highlight />
              <Stat label="vs baseline" value="7.0%" />
              <Stat label="Validity rate" value="94.0%" />
              <Stat label="Test set" value="200 pairs" />
            </div>
          </div>
        </section>

        {/* ── Demo (placeholder) ─────────────────────────────────────── */}
        <section
          id="demo"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel>Try it</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-12 tracking-tight">
            Ask anything across five schemas.
          </h2>

          <Placeholder height="h-[600px]">
            Demo component goes here — schema tabs, question input,
            streaming SQL output, results table.
          </Placeholder>
        </section>

        {/* ── Metrics (placeholder) ──────────────────────────────────── */}
        <section
          id="metrics"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel variant="accent">The numbers</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-12 tracking-tight">
            Fine-tuning works.
          </h2>

          <Placeholder height="h-[400px]">
            Comparison chart: baseline vs fine-tuned. Per-schema breakdown.
            Per-complexity breakdown.
          </Placeholder>
        </section>

        {/* ── How it works (placeholder) ─────────────────────────────── */}
        <section
          id="how"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel>How it works</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-12 tracking-tight">
            From question to validated SQL.
          </h2>

          <Placeholder height="h-[500px]">
            Architecture diagram: FastAPI → pgvector RAG → SageMaker
            (LoRA + bf16) → executor with self-correction.
          </Placeholder>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}

/* ── Local components ────────────────────────────────────────────── */

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`
        rounded-md px-3 py-2 border
        ${
          highlight
            ? "bg-primary/10 border-primary/30 text-primary"
            : "bg-muted/30 border-border text-muted-foreground"
        }
      `}
    >
      <span className="opacity-60 mr-2">{label}</span>
      <span className={highlight ? "text-primary" : "text-foreground"}>
        {value}
      </span>
    </div>
  );
}

function Placeholder({
  children,
  height,
}: {
  children: React.ReactNode;
  height: string;
}) {
  return (
    <div
      className={`
        glass rounded-2xl ${height}
        flex items-center justify-center
        border-dashed
        text-sm font-mono text-muted-foreground/60
        text-center px-8
      `}
    >
      {children}
    </div>
  );
}