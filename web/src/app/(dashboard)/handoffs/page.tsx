import { HandoffQueue } from "@/components/handoff-queue";

export default function HandoffsPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-foreground">Escalation & Handoff Queue</h1>
        <p className="text-sm text-muted">Leads currently in handoff-required state for operator triage.</p>
      </header>
      <HandoffQueue />
    </div>
  );
}

