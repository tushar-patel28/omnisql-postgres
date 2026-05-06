import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { SectionLabel } from "@/components/section-label";
import { DemoBanner } from "@/components/demo-banner";
import { DemoExperience } from "@/components/demo/demo-experience";
import { MetricsSection } from "@/components/metrics-section";
import { ArchitectureSection } from "@/components/architecture-section";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <DemoBanner />

      <main>
        {/* ── Hero ───────────────────────────────────────────────────── */}
        <section className="max-w-7xl mx-auto px-6 pt-24 pb-32">
          <div className="max-w-3xl">
            <h1 className="font-display text-5xl md:text-7xl leading-[1.05] tracking-tight">
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
              <Stat label="Execution accuracy" value="46.0%" />
              <Stat label="vs baseline" value="7.0%" />
              <Stat label="Validity rate" value="94.0%" />
              <Stat label="Test set" value="200 pairs" />
            </div>
          </div>
        </section>

        {/* ── Demo ───────────────────────────────────────────────────── */}
        <section
          id="demo"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel>Try it</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-12 tracking-tight">
            Ask anything across five schemas.
          </h2>

          <DemoExperience />
        </section>

        {/* ── Metrics ────────────────────────────────────────────────── */}
        <section
          id="metrics"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel variant="accent">The numbers</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-12 tracking-tight">
            Fine-tuning works.
          </h2>

          <MetricsSection />
        </section>

        {/* ── How it works ───────────────────────────────────────────── */}
        <section
          id="how"
          className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
        >
          <SectionLabel>How it works</SectionLabel>
          <h2 className="font-display text-4xl md:text-5xl mt-4 mb-4 tracking-tight">
            From question to validated SQL.
          </h2>
          <p className="text-muted-foreground mb-12 max-w-2xl">
            Click any stage to see implementation details.
          </p>

          <ArchitectureSection />
        </section>
      </main>

      <SiteFooter />
    </>
  );
}

/* ── Stat pill ─────────────────────────────────────────────────── */

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="
        rounded-md px-3 py-2
        glass
        text-muted-foreground
      "
    >
      <span className="opacity-60 mr-2">{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}