const PIPELINE_STAGES = [
  { stage: "new_lead → enriching", desc: "Ingest company id and pull public signals (funding, jobs, layoffs, leadership, tech)." },
  { stage: "brief_ready", desc: "ICP segment, AI maturity score, hiring signal brief, and competitor gap brief are attached." },
  { stage: "drafting → in_review", desc: "First-touch email drafted, then tone/claim review and policy checks before send." },
  { stage: "queued_to_send → awaiting_reply", desc: "Outbound sent; system waits for prospect email (or SMS where policy allows)." },
  { stage: "reply_received → qualifying", desc: "Inbound interpreted; next-best-action (clarify, nurture, schedule, escalate)." },
  { stage: "scheduling → booked", desc: "Cal.com-style booking with CRM sync on confirmation." },
  { stage: "nurture · handoff_required · closed", desc: "Long-cycle nurture, human takeover package, or terminal outcome." },
];

export function LandingContent() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">Conversion engine console</h1>
        <p className="max-w-3xl text-lg text-muted">
          This UI drives the <strong className="text-foreground">orchestration API</strong>: research-backed lead intake, briefs,
          outreach, replies, and scheduling—aligned to the Tenacious specs (signals, ICP, bench safety, CRM events).
        </p>
      </section>

      <section className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-foreground">What the pipeline does</h2>
        <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm text-muted md:text-base">
          <li>
            <span className="font-medium text-foreground">Discover &amp; enrich</span> — Merge Crunchbase firmographics with job posts,
            layoffs, leadership changes, and stack signals; attach confidence to each.
          </li>
          <li>
            <span className="font-medium text-foreground">Score &amp; classify</span> — AI maturity (0–3), ICP segment (with
            abstention when evidence is thin), competitor percentile and gap brief.
          </li>
          <li>
            <span className="font-medium text-foreground">Draft &amp; review outreach</span> — Segment-aware email grounded in
            briefs; reviewer enforces tone, claims, and bench commitment before send.
          </li>
          <li>
            <span className="font-medium text-foreground">Run conversations</span> — Replies interpreted; routing toward clarify,
            nurture, schedule, or human escalation.
          </li>
          <li>
            <span className="font-medium text-foreground">Book &amp; sync</span> — Meetings via Cal.com flow; HubSpot reflects stages
            and events.
          </li>
        </ol>
      </section>

      <section className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-foreground">Lead lifecycle (high level)</h2>
        <p className="mt-2 text-sm text-muted">
          States follow the runtime state machine: each transition is explicit, logged, and guardrailed in the API.
        </p>
        <ul className="mt-6 space-y-4">
          {PIPELINE_STAGES.map((row) => (
            <li key={row.stage} className="border-l-4 border-primary pl-4">
              <p className="font-mono text-sm font-semibold text-primary">{row.stage}</p>
              <p className="mt-1 text-sm text-muted">{row.desc}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-primary/30 bg-primary/5 p-6">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Ready to run intake?</h2>
          <p className="mt-1 text-sm text-muted">Open the pipeline, pick a company from the Crunchbase export, and process a lead.</p>
        </div>
      </section>
    </div>
  );
}
