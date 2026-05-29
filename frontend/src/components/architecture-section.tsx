"use client";

import { useState } from "react";
import {
  MessageSquareText,
  Cloud,
  Search,
  Cpu,
  CheckCircle2,
  ArrowRight,
  ChevronDown,
  type LucideIcon,
} from "lucide-react";

interface Node {
  icon: LucideIcon;
  label: string;
  sub?: string;
  badges: string[];
  tone: "muted" | "primary" | "accent" | "success";
  details: {
    summary: string;
    bullets: { title: string; body: string }[];
  };
}

const NODES: Node[] = [
  {
    icon: MessageSquareText,
    label: "Natural-language question",
    sub: "User input",
    badges: ["plain English"],
    tone: "muted",
    details: {
      summary:
        "Anything from a casual question to a multi-clause analytical request. The user picks which schema to query against (5 supported); no SQL knowledge required.",
      bullets: [
        {
          title: "Supported question shapes",
          body: "Filters, aggregates, joins, top-N, time windows, complex CTEs. Validated against 200 held-out test questions across 4 difficulty tiers.",
        },
        {
          title: "Privacy",
          body: "Questions are sent over HTTPS to the backend; no logging of PII, no third-party calls during inference.",
        },
      ],
    },
  },
  {
    icon: Cloud,
    label: "FastAPI on ECS Fargate",
    sub: "Behind an Application Load Balancer",
    badges: ["FastAPI", "Pydantic", "ECS", "ALB"],
    tone: "primary",
    details: {
      summary:
        "Stateless Python service running on Fargate. ALB handles TLS termination and routes /generate requests. Container is built for linux/amd64 from a Dockerfile and published to ECR.",
      bullets: [
        {
          title: "Why Fargate",
          body: "No EC2 management, scales to zero between invocations, ~$25/mo at idle. Cheaper than EC2 for portfolio traffic.",
        },
        {
          title: "Validation layer",
          body: "Pydantic schemas validate question shape, schema selection, and rate-limit headers. Rejects malformed payloads before they reach the model.",
        },
        {
          title: "Infrastructure",
          body: "All resources defined as Terraform modules (vpc.tf, ecs.tf, etc). One command spins up or tears down the entire stack.",
        },
      ],
    },
  },
  {
    icon: Search,
    label: "pgvector RAG retrieval",
    sub: "Top-K relevant tables for the question",
    badges: ["pgvector", "RDS Postgres", "OpenAI embeddings"],
    tone: "primary",
    details: {
      summary:
        "Each schema's table DDLs are embedded once at startup. At query time, the question is embedded and we retrieve the K most relevant table definitions to inject into the prompt — instead of dumping all 30+ tables.",
      bullets: [
        {
          title: "Why RAG over full schema",
          body: "Reduces prompt tokens by ~80%, improves accuracy on multi-schema queries, and keeps inference latency under 5s at p95.",
        },
        {
          title: "Embedding choice",
          body: "OpenAI text-embedding-3-small (1536-d). Cheap, multilingual, and good signal for SQL/DDL semantics. Computed once and cached in pgvector.",
        },
        {
          title: "Retrieval strategy",
          body: "Cosine similarity, top-K=5 by default. Falls back to full schema if K<3 tables clear a 0.5 similarity threshold.",
        },
      ],
    },
  },
  {
    icon: Cpu,
    label: "SageMaker async endpoint",
    sub: "OmniSQL-7B + LoRA adapter (37 MB)",
    badges: ["SageMaker", "QLoRA", "bf16", "ml.g5.2xlarge"],
    tone: "accent",
    details: {
      summary:
        "Async inference because g5.2xlarge inference takes 1-3s and we don't want to block ALB threads. Input lands in S3, endpoint polls, output comes back via S3.",
      bullets: [
        {
          title: "Fine-tuning recipe",
          body: "QLoRA r=16 alpha=32, lr=1e-4, 3 epochs on 2,400 PostgreSQL question/SQL pairs. Trained in 94 min on ml.g5.2xlarge. Loss dropped 0.65 → 0.13.",
        },
        {
          title: "bf16, not fp16",
          body: "Critical for Qwen2 base. fp16 produces token-0 contamination (`!` everywhere) and NaN gradients during training. bf16 fixes both.",
        },
        {
          title: "37 MB adapter",
          body: "LoRA only updates 0.5% of parameters. The base 7B model stays frozen and the small adapter loads at startup. Easy to A/B test new adapters.",
        },
        {
          title: "Eval result",
          body: "69% execution accuracy on 200 held-out queries vs 23% for the zero-shot baseline under matched beam-search decoding — a 3.0× improvement attributable to fine-tuning.",
        },
      ],
    },
  },
  {
    icon: CheckCircle2,
    label: "Executor with self-correction",
    sub: "Validates SQL · retries up to 2× on errors",
    badges: ["SQLAlchemy", "execution check"],
    tone: "primary",
    details: {
      summary:
        "Generated SQL is run against a sandboxed Postgres instance. Syntax errors, type errors, or missing columns trigger a retry where the error message is appended to the prompt and the model gets one more chance.",
      bullets: [
        {
          title: "Retry strategy",
          body: "Up to 2 retries with the previous SQL + error message in context. Most simple errors (missing FROM, bad column names) self-correct on retry 1.",
        },
        {
          title: "Sandboxing",
          body: "Read-only role, statement timeout 5s, no DDL allowed. Safe to run user-driven SQL without risk of data corruption.",
        },
      ],
    },
  },
  {
    icon: ArrowRight,
    label: "Validated SQL + result rows",
    sub: "Returned as JSON",
    badges: ["JSON response"],
    tone: "success",
    details: {
      summary:
        "Final response is a JSON object: the validated SQL, the result row set (capped at 100 rows for display), execution metadata (latency, retries used), and a unique request ID for log correlation.",
      bullets: [
        {
          title: "What the demo shows",
          body: "The streaming SQL output and the result table you see above are exactly what the API returns — only the bytes have been pre-recorded for $0 hosting.",
        },
      ],
    },
  },
];

const TONES = {
  muted:   { ring: "rgba(232,234,242,0.12)", glow: "rgba(232,234,242,0.06)" },
  primary: { ring: "rgba(110,168,255,0.30)", glow: "rgba(110,168,255,0.20)" },
  accent:  { ring: "rgba(192,132,255,0.40)", glow: "rgba(192,132,255,0.28)" },
  success: { ring: "rgba(74,222,128,0.30)",  glow: "rgba(74,222,128,0.18)" },
} as const;

export function ArchitectureSection() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <div className="relative max-w-3xl mx-auto">
      {/* Animated flow line */}
      <div className="absolute left-1/2 top-12 bottom-12 w-px -translate-x-1/2 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-border to-transparent" />
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

      <div className="relative space-y-6">
        {NODES.map((node, i) => (
          <FlowNode
            key={i}
            node={node}
            index={i}
            isOpen={openIdx === i}
            onToggle={() => setOpenIdx(openIdx === i ? null : i)}
          />
        ))}
      </div>

      <style jsx>{`
        @keyframes flow-down {
          0%   { top: -12%; opacity: 0; }
          15%  { opacity: 1; }
          85%  { opacity: 1; }
          100% { top: 112%; opacity: 0; }
        }
      `}</style>
    </div>
  );
}

function FlowNode({
  node,
  index,
  isOpen,
  onToggle,
}: {
  node: Node;
  index: number;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const Icon = node.icon;
  const tone = TONES[node.tone];

  return (
    <div className="relative flex items-stretch gap-5 group">
      {/* Step number column */}
      <div className="flex flex-col items-center pt-5 w-10">
        <div
          className="
            w-9 h-9 rounded-full glass
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

      {/* Node card (clickable) */}
      <div className="flex-1">
        <button
          onClick={onToggle}
          aria-expanded={isOpen}
          className={`
            w-full text-left glass rounded-xl p-5
            transition-all duration-300
            cursor-pointer
            ${isOpen ? "translate-x-1" : "group-hover:translate-x-1"}
          `}
          style={{ boxShadow: `inset 0 0 0 1px ${tone.ring}` }}
        >
          <div className="flex items-start gap-4">
            <div
              className="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
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
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-lg leading-tight">
                    {node.label}
                  </div>
                  {node.sub && (
                    <div className="mt-1 text-sm text-muted-foreground">
                      {node.sub}
                    </div>
                  )}
                </div>
                <ChevronDown
                  className={`
                    w-4 h-4 text-muted-foreground/60 mt-1 shrink-0
                    transition-transform duration-300
                    ${isOpen ? "rotate-180" : ""}
                  `}
                />
              </div>

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
        </button>

        {/* Expanded details */}
        {isOpen && (
          <div
            className="
              mt-2 ml-2 glass rounded-xl p-5 pl-6
              border-l-2
              animate-in fade-in slide-in-from-top-2 duration-300
            "
            style={{
              borderLeftColor: tone.ring.replace("0.30", "0.5").replace("0.40", "0.6"),
            }}
          >
            <p className="text-sm text-foreground/80 leading-relaxed mb-4">
              {node.details.summary}
            </p>
            <div className="space-y-3">
              {node.details.bullets.map((b, i) => (
                <div key={i}>
                  <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-1">
                    {b.title}
                  </div>
                  <p className="text-sm text-foreground/70 leading-relaxed">
                    {b.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}