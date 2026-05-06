"use client";

import { ArrowRight, Sparkles, Loader2 } from "lucide-react";
import { useState } from "react";
import type { DemoExample } from "@/lib/demo-data";

interface QuestionInputProps {
  examples: DemoExample[];
  onSubmit: (example: DemoExample) => void;
  isLoading: boolean;
}

export function QuestionInput({
  examples,
  onSubmit,
  isLoading,
}: QuestionInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    if (isLoading || examples.length === 0) return;

    // Match by question text (case-insensitive partial match) or random
    const trimmed = value.trim().toLowerCase();
    const match = examples.find((ex) =>
      ex.question.toLowerCase().includes(trimmed)
    );
    onSubmit(match ?? examples[0]);
  };

  const handleChipClick = (ex: DemoExample) => {
    setValue(ex.question);
    onSubmit(ex);
  };

  return (
    <div className="space-y-4">
      {/* Input area */}
      <div
        className="
          glass rounded-2xl p-1.5
          focus-within:ring-1 focus-within:ring-primary/40
          transition-all
        "
      >
        <div className="flex items-end gap-2">
          <div className="flex-1 px-4 pt-3 pb-2">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-3.5 h-3.5 text-accent" />
              <span className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                Ask in plain English
              </span>
            </div>
            <textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              rows={2}
              placeholder="e.g. What are the top products by revenue last month?"
              className="
                w-full bg-transparent resize-none
                text-base text-foreground
                placeholder:text-muted-foreground/50
                focus:outline-none
                font-display
              "
              disabled={isLoading}
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="
              m-1 px-5 py-3
              rounded-xl
              bg-primary text-primary-foreground
              font-mono text-sm
              flex items-center gap-2
              transition-all
              hover:bg-primary/90 hover:shadow-[0_0_24px_-4px_var(--primary)]
              disabled:opacity-50 disabled:cursor-not-allowed
              active:scale-[0.98]
            "
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating
              </>
            ) : (
              <>
                Run
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Example chips */}
      <div className="flex flex-wrap gap-2">
        <span className="text-xs font-mono text-muted-foreground/60 self-center mr-1">
          Try:
        </span>
        {examples.slice(0, 3).map((ex) => (
          <button
            key={ex.id}
            onClick={() => handleChipClick(ex)}
            disabled={isLoading}
            className="
              text-xs font-mono
              px-3 py-1.5 rounded-full
              border border-border
              text-muted-foreground hover:text-foreground
              hover:border-primary/40 hover:bg-primary/5
              transition-all
              disabled:opacity-40 disabled:cursor-not-allowed
              max-w-[420px] truncate
            "
            title={ex.question}
          >
            {ex.question}
          </button>
        ))}
      </div>
    </div>
  );
}