import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function DataTable({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("overflow-auto rounded-md border border-border bg-surface", className)}>{children}</div>;
}

export function DataTableElement({ className, children }: { className?: string; children: ReactNode }) {
  return <table className={cn("min-w-full text-left text-sm", className)}>{children}</table>;
}

