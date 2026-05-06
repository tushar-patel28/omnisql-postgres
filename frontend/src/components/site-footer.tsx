import { Code2 } from "lucide-react";

export function SiteFooter() {
  return (
    <footer className="border-t border-border/40 mt-32">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="space-y-1">
            <p className="font-display text-lg">
              OmniSQL <span className="text-foreground/60">Postgres</span>
            </p>
            <p className="font-mono text-xs text-muted-foreground">
              Fine-tuning research · MS SE @ Northeastern
            </p>
          </div>

          <div className="flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-8 text-xs font-mono">
            <a
              href="https://arxiv.org/abs/2503.02240"
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              OmniSQL paper
            </a>
            <a
              href="https://huggingface.co/seeklhy/OmniSQL-7B"
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              Base model
            </a>
            <a
              href="https://github.com/tushar-patel28/omnisql-postgres"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              Source
            </a>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-border/30 text-xs font-mono text-muted-foreground/60">
          Demo runs on pre-recorded model outputs to keep hosting at $0.
          The model itself is real — see GitHub for live deployment.
        </div>
      </div>
    </footer>
  );
}