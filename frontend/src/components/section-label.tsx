interface SectionLabelProps {
  children: React.ReactNode;
  variant?: "primary" | "accent";
}

export function SectionLabel({
  children,
  variant = "primary",
}: SectionLabelProps) {
  const dotColor = variant === "accent" ? "bg-accent" : "bg-primary";

  return (
    <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
      <span
        className={`w-1.5 h-1.5 rounded-full animate-pulse-soft ${dotColor}`}
      />
      {children}
    </div>
  );
}