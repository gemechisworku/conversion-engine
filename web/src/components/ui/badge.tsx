import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

const toneClass: Record<BadgeTone, string> = {
  neutral: "bg-background text-foreground border-border",
  info: "bg-primary/15 text-primary border-primary/25",
  success: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  warning: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  danger: "bg-danger/15 text-danger border-danger/30",
};

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  const tone = props.tone ?? "neutral";
  const rest = { ...props } as HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone };
  delete rest.tone;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        toneClass[tone],
        className,
      )}
      {...rest}
    />
  );
}
