"use client";

import {
  MessageSquareText,
  Cloud,
  Search,
  Cpu,
  CheckCircle2,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";

interface Node {
  icon: LucideIcon;
  label: string;
  sub?: string;
  badges: string[];
  tone: "muted" | "primary" | "accent" | "success";
}

const NODES: Node[] = [
  {
    icon: MessageSquareText,
    label: "Natural-language question",
    sub: "User input",
    badges: ["plain English"],
    tone: "muted",
  },
  {
    icon: Cloud,
    label: "FastAPI on ECS Fargate",
    sub: "Behind an Application Load Balancer",
    badges: ["FastAPI", "Pydantic", "ECS", "ALB"],
    tone: "primary",
  },
  {
    icon: Search,
    label: "pgvector RAG retrieval",
    sub: "Top-K relevant tables for the question",
    badges: ["pgvector", "RDS Postgres", "OpenAI embeddings"],
    tone: "primary",
  },
  {
    icon: Cpu,
    label: "SageMaker async endpoint",
    sub: "OmniSQL-7B + LoRA adapter (37 MB)",
    badges: ["SageMaker", "QLoRA", "bf16", "ml.g5.2xlarge"],
    tone: "accent",
  },
  {
    icon: CheckCircle2,
    label: "Executor with self-correction",
    sub: "Validates SQL · retries up to 2× on errors",
    badges: ["SQLAlchemy", "execution check"],
    tone: "primary",
  },
  {
    icon: ArrowRight,
    label: "Validated SQL + result rows",
    sub: "Returned as JSON",
    badges: ["JSON response"],
    tone: "success",
  },
];

const TONES = {
  muted:   { ring: "rgba(232,234,242,0.12)",  glow: "rgba(232,234,242,0.06)" },
  primary: { ring: "rgba(110,168,255,0.30)",  glow: "rgba(110,168,255,0.20)" },
  accent:  { ring: "rgba(192,132,255,0.40)",  glow: "rgba(192,132,255,0.28)" },
  success: { ring: "rgba(74,222,128,0.30)",   glow: "rgba(74,222,128,0.18)" },
} as const;

export function ArchitectureSection() {
  return (
    <div className="relative max-w-3xl mx-auto">
      {/* The animated flowing line behind everything */}
      <div className="absolute left-1/2 top-12 bottom-12 w-px -translate-x-1/2 pointer-events-none">
        {/* Static base line */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-border to-transparent" />
        {/* Animated traveling pulse */}
        <div
          className="absolute left-1/2 -translate-x-1/2 w-px h-24 rounded-full"
          style={{
            background:
              "linear-gradient(180deg, transparent, var(--primary), var(--accent), transparent)",
            filter: "blur(0.5px)",
            animation: "flow-down 4.5s linear infinite",
          }}
        />
      </div>

      {/* Nodes */}
      <div className="relative space-y-6">
        {NODES.map((node, i) => (
          <FlowNode key={i} node={node} index={i} />
        ))}
      </div>

      {/* Keyframes */}
      <style jsx>{`
        @keyframes flow-down {
          0% {
            top: -12%;
            opacity: 0;
          }
          15% {
            opacity: 1;
          }
          85% {
            opacity: 1;
          }
          100% {
            top: 112%;
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}

function FlowNode({ node, index }: { node: Node; index: number }) {
  const Icon = node.icon;
  const tone = TONES[node.tone];

  return (
    <div className="relative flex items-stretch gap-5 group">
      {/* Step number column */}
      <div className="flex flex-col items-center pt-5 w-10">
        <div
          className="
            w-9 h-9 rounded-full
            glass
            flex items-center justify-center
            text-xs font-mono text-muted-foreground
            relative z-10
          "
          style={{
            boxShadow: `inset 0 0 0 1px ${tone.ring}, 0 0 24px -8px ${tone.glow}`,
          }}
        >
          {String(index + 1).padStart(2, "0")}
        </div>
      </div>

      {/* Node card */}
      <div
        className="
          flex-1 glass rounded-xl p-5
          transition-all duration-300
          group-hover:translate-x-1
        "
        style={{
          boxShadow: `inset 0 0 0 1px ${tone.ring}`,
        }}
      >
        <div className="flex items-start gap-4">
          <div
            className="
              shrink-0 w-10 h-10 rounded-lg
              flex items-center justify-center
              relative
            "
            style={{
              background: tone.glow,
              boxShadow: `0 0 20px -4px ${tone.glow}`,
            }}
          >
            <Icon
              className="w-5 h-5"
              strokeWidth={1.75}
              style={{
                color:
                  node.tone === "primary"
                    ? "var(--primary)"
                    : node.tone === "accent"
                    ? "var(--accent)"
                    : node.tone === "success"
                    ? "var(--chart-3)"
                    : "var(--foreground)",
              }}
            />
          </div>

          <div className="flex-1 min-w-0">
            <div className="font-display text-lg leading-tight">
              {node.label}
            </div>
            {node.sub && (
              <div className="mt-1 text-sm text-muted-foreground">
                {node.sub}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-1.5">
              {node.badges.map((b) => (
                <span
                  key={b}
                  className="
                    text-[10px] font-mono uppercase tracking-wider
                    px-2 py-0.5 rounded
                    bg-foreground/[0.04] text-muted-foreground
                    border border-border/40
                  "
                >
                  {b}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}