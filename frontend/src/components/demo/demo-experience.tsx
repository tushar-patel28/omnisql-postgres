"use client";

import { useMemo, useState } from "react";
import { Brain } from "lucide-react";
import {
  DEMO_EXAMPLES,
  SCHEMAS,
  type DemoExample,
  type SchemaName,
} from "@/lib/demo-data";
import { SchemaTabs } from "./schema-tabs";
import { QuestionInput } from "./question-input";
import { StreamingSql } from "./streaming-sql";
import { ResultsTable } from "./results-table";

const THINK_MS = 1500;

type Phase = "idle" | "thinking" | "streaming" | "done";

export function DemoExperience() {
  const [activeSchema, setActiveSchema] = useState<SchemaName>("ecommerce");
  const [activeExample, setActiveExample] = useState<DemoExample | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");

  const examplesForSchema = useMemo(
    () => DEMO_EXAMPLES.filter((ex) => ex.schema === activeSchema),
    [activeSchema]
  );

  const handleSubmit = (example: DemoExample) => {
    setActiveExample(example);
    setPhase("thinking");
    setTimeout(() => setPhase("streaming"), THINK_MS);
  };

  const handleSchemaChange = (s: SchemaName) => {
    setActiveSchema(s);
    setActiveExample(null);
    setPhase("idle");
  };

  return (
    <div className="space-y-6">
      {/* Schema tabs */}
      <SchemaTabs active={activeSchema} onChange={handleSchemaChange} />

      {/* Question input */}
      <QuestionInput
        examples={examplesForSchema}
        onSubmit={handleSubmit}
        isLoading={phase === "thinking" || phase === "streaming"}
      />

      {/* Output area */}
      {phase === "idle" && <IdleState schema={activeSchema} />}

      {phase === "thinking" && <ThinkingState />}

      {(phase === "streaming" || phase === "done") && activeExample && (
        <div className="space-y-4 animate-in fade-in duration-500">
          <StreamingSql
            sql={activeExample.generatedSql}
            triggerKey={activeExample.id}
            speedMs={6}
            onComplete={() => setPhase("done")}
          />

          {phase === "done" && (
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
              <ResultsTable example={activeExample} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── States ──────────────────────────────────────────────────────── */

function IdleState({ schema }: { schema: SchemaName }) {
  const meta = SCHEMAS[schema];
  return (
    <div
      className="
        glass rounded-2xl
        h-[280px]
        flex flex-col items-center justify-center
        text-center px-8
        border-dashed
      "
    >
      <div
        className="text-xs font-mono uppercase tracking-widest mb-3"
        style={{ color: meta.color }}
      >
        {meta.label} schema selected
      </div>
      <p className="font-display text-2xl text-foreground/80 max-w-md">
        Type a question or pick an example above to see the model in action.
      </p>
    </div>
  );
}

function ThinkingState() {
  return (
    <div
      className="
        glass rounded-2xl h-[280px]
        flex flex-col items-center justify-center
        text-center px-8
      "
    >
      <div className="relative mb-4">
        <div className="absolute inset-0 blur-2xl bg-primary/40 animate-pulse" />
        <Brain className="relative w-10 h-10 text-primary" strokeWidth={1.5} />
      </div>

      <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-primary">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
        </span>
        Thinking
      </div>

      <p className="mt-3 font-display text-lg text-muted-foreground">
        Running schema retrieval, prompt construction, and inference.
      </p>
    </div>
  );
}