"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <span className="inline-flex h-9 w-24 rounded-md border border-border bg-surface" aria-hidden />
    );
  }

  const cycle = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  const label =
    theme === "system" ? `System (${resolvedTheme === "dark" ? "dark" : "light"})` : theme === "dark" ? "Dark" : "Light";

  return (
    <button
      type="button"
      onClick={cycle}
      className="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium text-foreground shadow-sm transition hover:bg-background"
      aria-label={`Theme: ${label}. Click to cycle light, dark, and system.`}
    >
      <span className="text-muted">Theme</span>
      <span className="rounded bg-primary/15 px-2 py-0.5 text-primary capitalize">{label}</span>
    </button>
  );
}
