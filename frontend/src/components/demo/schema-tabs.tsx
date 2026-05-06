"use client";

import {
  ShoppingBag,
  Banknote,
  Stethoscope,
  Users,
  BarChart3,
  type LucideIcon,
} from "lucide-react";
import { SCHEMAS, type SchemaName } from "@/lib/demo-data";

const ICON_MAP: Record<string, LucideIcon> = {
  ShoppingBag,
  Banknote,
  Stethoscope,
  Users,
  BarChart3,
};

interface SchemaTabsProps {
  active: SchemaName;
  onChange: (schema: SchemaName) => void;
}

export function SchemaTabs({ active, onChange }: SchemaTabsProps) {
  return (
    <div
      role="tablist"
      className="
        flex flex-wrap gap-2 p-1.5
        glass rounded-xl
        w-fit
      "
    >
      {(Object.keys(SCHEMAS) as SchemaName[]).map((name) => {
        const meta = SCHEMAS[name];
        const Icon = ICON_MAP[meta.icon];
        const isActive = active === name;

        return (
          <button
            key={name}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(name)}
            className={`
              flex items-center gap-2 px-4 py-2.5
              text-sm font-mono
              rounded-lg
              transition-all duration-200
              ${
                isActive
                  ? "bg-foreground/[0.06] text-foreground shadow-[inset_0_0_0_1px_rgba(232,234,242,0.08)]"
                  : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.03]"
              }
            `}
            style={
              isActive
                ? { boxShadow: `inset 0 0 0 1px ${meta.color}40, 0 0 24px -8px ${meta.color}80` }
                : undefined
            }
          >
            <Icon
              className="w-4 h-4"
              strokeWidth={1.75}
              style={{ color: isActive ? meta.color : undefined }}
            />
            {meta.label}
          </button>
        );
      })}
    </div>
  );
}