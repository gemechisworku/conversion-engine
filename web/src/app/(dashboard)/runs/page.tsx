"use client";

import { PipelineRunsList } from "@/components/pipeline-runs-list";

export default function PipelineRunsPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Pipeline Runs</h1>
        <p className="mt-1 text-sm text-muted">
          All companies processed by the pipeline. Re-runs update the same company row and increment run count.
        </p>
      </div>
      <PipelineRunsList refreshToken={0} />
    </div>
  );
}

