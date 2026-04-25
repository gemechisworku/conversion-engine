import { ControlTower } from "@/components/control-tower";

export default function ControlPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-foreground">Observability Control Tower</h1>
        <p className="text-sm text-muted">
          Operational view across pipelines, outreach, handoffs, and browser-captured API trace diagnostics.
        </p>
      </header>
      <ControlTower />
    </div>
  );
}

