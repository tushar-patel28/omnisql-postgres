"use client";

import { useEffect, useState, useRef } from "react";
import { Check, Copy, Code2 } from "lucide-react";

interface StreamingSqlProps {
  sql: string;
  /** When this changes, animation restarts */
  triggerKey: string;
  /** ms per character — lower = faster */
  speedMs?: number;
  /** Called when streaming completes */
  onComplete?: () => void;
}

export function StreamingSql({
  sql,
  triggerKey,
  speedMs = 8,
  onComplete,
}: StreamingSqlProps) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);
  const [copied, setCopied] = useState(false);
  const onCompleteRef = useRef(onComplete);

  // Keep the latest callback without re-triggering the streaming effect
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    setDisplayed("");
    setDone(false);

    let i = 0;
    const interval = setInterval(() => {
      // Advance by 2-4 characters each tick for a more natural feel
      const step = 2 + Math.floor(Math.random() * 3);
      i = Math.min(i + step, sql.length);
      setDisplayed(sql.slice(0, i));

      if (i >= sql.length) {
        clearInterval(interval);
        setDone(true);
        onCompleteRef.current?.();
      }
    }, speedMs);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerKey, sql, speedMs]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="glass rounded-xl overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-foreground/[0.02]">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
          <Code2 className="w-3.5 h-3.5 text-primary" />
          <span>generated_sql</span>
          <span className="text-muted-foreground/40">·</span>
          <span className="text-muted-foreground/60">postgresql</span>
        </div>

        <button
          onClick={handleCopy}
          disabled={!done}
          className="
            flex items-center gap-1.5
            text-xs font-mono
            text-muted-foreground hover:text-foreground
            transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed
          "
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-chart-3" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>

      {/* SQL body */}
      <pre
        className="
          px-5 py-4 overflow-x-auto
          text-sm font-mono leading-relaxed
          text-foreground/90
          whitespace-pre-wrap break-words
          min-h-[120px]
        "
      >
        <code className="block">
          <SqlHighlighted sql={displayed} />
          {!done && (
            <span className="inline-block w-1.5 h-4 bg-primary ml-0.5 align-middle animate-pulse" />
          )}
        </code>
      </pre>
    </div>
  );
}

/* ── Tiny SQL syntax highlighter ─────────────────────────────────── */

const KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
  "ON", "AND", "OR", "NOT", "IN", "IS", "NULL", "AS", "GROUP", "BY",
  "ORDER", "HAVING", "LIMIT", "OFFSET", "DISTINCT", "WITH", "UNION",
  "INSERT", "UPDATE", "DELETE", "VALUES", "SET", "INTO", "CASE", "WHEN",
  "THEN", "ELSE", "END", "INTERVAL", "EXTRACT", "DATE_TRUNC", "NOW",
  "COUNT", "SUM", "AVG", "MIN", "MAX", "CAST", "ILIKE", "LIKE", "OVER",
  "PARTITION", "ROW_NUMBER", "AGE", "CURRENT_DATE", "DESC", "ASC",
]);

function SqlHighlighted({ sql }: { sql: string }) {
  // Tokenize while preserving whitespace and punctuation
  const tokens = sql.split(/(\s+|[(),;.])/);

  return (
    <>
      {tokens.map((tok, i) => {
        if (!tok) return null;

        const upper = tok.toUpperCase();
        if (KEYWORDS.has(upper)) {
          return (
            <span key={i} className="text-primary font-medium">
              {tok}
            </span>
          );
        }

        // String literals
        if (/^'[^']*'$/.test(tok)) {
          return (
            <span key={i} className="text-chart-3">
              {tok}
            </span>
          );
        }

        // Numbers
        if (/^\d+(\.\d+)?$/.test(tok)) {
          return (
            <span key={i} className="text-chart-4">
              {tok}
            </span>
          );
        }

        // Schema-qualified table refs (e.g. fintech.accounts)
        if (/^\w+\.\w+$/.test(tok)) {
          const [schema, table] = tok.split(".");
          return (
            <span key={i}>
              <span className="text-accent">{schema}</span>
              <span className="text-muted-foreground">.</span>
              <span className="text-foreground/90">{table}</span>
            </span>
          );
        }

        return <span key={i}>{tok}</span>;
      })}
    </>
  );
}