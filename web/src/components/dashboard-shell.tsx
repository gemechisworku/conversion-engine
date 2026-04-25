"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

const nav = [
  { href: "/", label: "Overview" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/runs", label: "Pipeline Runs" },
  { href: "/outreachs", label: "Outreachs" },
  { href: "/handoffs", label: "Handoffs" },
  { href: "/control", label: "Control Tower" },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-border bg-surface md:w-56 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between gap-2 p-4 md:flex-col md:items-stretch">
          <Link href="/" className="text-lg font-semibold tracking-tight text-foreground">
            Tenacious<span className="text-primary">Ops</span>
          </Link>
          <nav className="flex flex-wrap gap-2 md:flex-col">
            {nav.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                    active ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-background"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface px-4 py-3">
          <p className="text-sm text-muted">Conversion engine · orchestration UI</p>
          <ThemeToggle />
        </header>
        <main className="flex-1 bg-background p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
