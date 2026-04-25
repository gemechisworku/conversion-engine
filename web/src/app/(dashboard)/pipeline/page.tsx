"use client";

import { HealthStatus } from "@/components/health-status";
import { PipelineRunsList } from "@/components/pipeline-runs-list";
import { ProcessLeadForm } from "@/components/process-lead-form";
import { useState } from "react";

export default function PipelinePage() {
  const [refreshToken, setRefreshToken] = useState(0);
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Pipeline</h1>
        <p className="mt-1 text-sm text-muted">
          Check API health, select a company from the Crunchbase export, then run intake to open the lead detail view.
        </p>
      </div>
      <HealthStatus />
      <ProcessLeadForm onPipelineChanged={() => setRefreshToken((n) => n + 1)} />
      <PipelineRunsList refreshToken={refreshToken} />
    </div>
  );
}
