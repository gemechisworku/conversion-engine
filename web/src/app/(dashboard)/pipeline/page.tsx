"use client";

import { ProcessLeadForm } from "@/components/process-lead-form";

export default function PipelinePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Pipeline</h1>
        <p className="mt-1 text-sm text-muted">Select a company from the Crunchbase export and run intake.</p>
      </div>
      <ProcessLeadForm />
    </div>
  );
}
