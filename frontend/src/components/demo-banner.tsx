"use client";

import { useState } from "react";
import { Info, X } from "lucide-react";

export function DemoBanner() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div
      className="
        border-b border-border/40
        bg-muted/30 backdrop-blur-md
      "
    >
      <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center gap-3">
        <Info className="w-3.5 h-3.5 text-accent shrink-0" />
        <p className="flex-1 text-xs font-mono text-muted-foreground">
          <span className="text-foreground/80">Demo mode</span>
          {" — "}
          this site replays recorded outputs from the real fine-tuned model to keep hosting at $0.
          The model and metrics are real;{" "}
          <a
            href="https://github.com/tushar-patel28/omnisql-postgres"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground/80 hover:text-primary transition-colors underline-offset-2 hover:underline"
          >
            see the repo
          </a>
          {" "}to run live inference.
        </p>
        <button
          onClick={() => setDismissed(true)}
          className="
            shrink-0 p-1 rounded
            text-muted-foreground/60 hover:text-foreground
            hover:bg-foreground/[0.05]
            transition-all
          "
          aria-label="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}