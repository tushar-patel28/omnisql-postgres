import { Database, Sparkles } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      {/* Wordmark */}
      <div className="flex items-center gap-3 mb-12">
        <div className="relative">
          <div className="absolute inset-0 blur-xl bg-primary/40" />
          <Database className="relative w-10 h-10 text-primary" strokeWidth={1.5} />
        </div>
        <h1 className="text-5xl font-display tracking-tight">
          <span className="gradient-text">OmniSQL</span>
          <span className="text-foreground/80"> Postgres</span>
        </h1>
      </div>

      {/* Theme test card */}
      <div className="glass rounded-2xl p-10 max-w-xl w-full">
        <div className="flex items-center gap-2 mb-6 text-xs font-mono uppercase tracking-widest text-muted-foreground">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse-soft" />
          Theme test
        </div>

        <h2 className="font-display text-3xl mb-3 leading-tight">
          A natural-language SQL engine,
          <br />
          fine-tuned for PostgreSQL.
        </h2>

        <p className="text-muted-foreground mb-6 leading-relaxed">
          Built on OmniSQL-7B with QLoRA fine-tuning on 1,800 PostgreSQL
          query pairs. Deployed as a SageMaker async inference endpoint.
        </p>

        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20">
            46.0% EX
          </span>
          <span className="text-muted-foreground">vs</span>
          <span className="px-2 py-1 rounded bg-muted text-muted-foreground border border-border">
            7.0% baseline
          </span>
          <Sparkles className="w-3.5 h-3.5 text-accent ml-auto" />
        </div>
      </div>

      <p className="mt-8 text-xs font-mono text-muted-foreground/60">
        theme.test.tsx · ready
      </p>
    </main>
  );
}