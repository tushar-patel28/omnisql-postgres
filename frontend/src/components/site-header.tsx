"use client";

import Link from "next/link";
import { Database, Code2 } from "lucide-react";

const NAV = [
  { href: "#demo",      label: "Demo" },
  { href: "#metrics",   label: "Metrics" },
  { href: "#how",       label: "How it works" },
];

export function SiteHeader() {
  return (
    <header
      className="
        sticky top-0 z-50
        border-b border-border/40
        backdrop-blur-2xl bg-background/40
      "
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo / wordmark */}
        <Link
          href="/"
          className="flex items-center gap-2.5 group"
        >
          <div className="relative">
            <div className="absolute inset-0 blur-md bg-primary/40 group-hover:bg-primary/60 transition-colors" />
            <Database
              className="relative w-5 h-5 text-primary"
              strokeWidth={1.75}
            />
          </div>
          <span className="font-display text-xl tracking-tight text-foreground">
            OmniSQL <span className="text-foreground/60">Postgres</span>
          </span>
        </Link>

        {/* Nav */}
        <nav className="hidden md:flex items-center gap-8 text-sm font-mono">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="
                text-muted-foreground hover:text-foreground
                transition-colors relative
                after:content-['']
                after:absolute after:left-0 after:right-0 after:-bottom-1
                after:h-px after:bg-primary
                after:scale-x-0 hover:after:scale-x-100
                after:origin-left after:transition-transform
              "
            >
              {item.label}
            </a>
          ))}
        </nav>

        {/* GitHub */}
        <a
          href="https://github.com/tushar-patel28/omnisql-postgres"
          target="_blank"
          rel="noopener noreferrer"
          className="
            flex items-center gap-2 text-sm font-mono
            text-muted-foreground hover:text-foreground
            transition-colors
            border border-border/60 hover:border-border
            rounded-md px-3 py-1.5
          "
        >
          <Code2 className="w-4 h-4" />
          <span className="hidden sm:inline">GitHub</span>
        </a>
      </div>
    </header>
  );
}