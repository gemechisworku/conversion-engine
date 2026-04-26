import Link from "next/link";

// Implements: FR-1, FR-2, FR-7, FR-8, FR-9, FR-11, FR-12, FR-15
// Workflow: lead_intake_and_enrichment.md, outreach_generation_and_review.md, reply_handling.md, scheduling_and_booking.md
// Schema: lead_object.md, conversation_state.md, booking_event.md, trace_event.md
// API: overview.md, orchestration_api.md, outreach_api.md, scheduling_api.md, crm_api.md

type WorkflowStep = {
  id: string;
  title: string;
  state: string;
  detail: string;
};

const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "intake",
    title: "Lead Intake",
    state: "new_lead -> enriching",
    detail: "Create lead context, start trace, and launch public-data signal collection.",
  },
  {
    id: "signals",
    title: "Signal Research",
    state: "enriching",
    detail: "Collect funding, hiring, layoffs, leadership, and stack evidence with confidence hints.",
  },
  {
    id: "brief",
    title: "Brief Ready",
    state: "enriching -> brief_ready",
    detail: "Attach hiring brief, AI maturity score, competitor gap, and ICP classification.",
  },
  {
    id: "review",
    title: "Draft + Review",
    state: "brief_ready -> in_review",
    detail: "Generate outreach, validate claims and tone, and run pre-send policy checks.",
  },
  {
    id: "send",
    title: "Send",
    state: "queued_to_send -> awaiting_reply",
    detail: "Queue or send the approved message, then persist message and CRM events.",
  },
  {
    id: "reply",
    title: "Reply Routing",
    state: "awaiting_reply -> reply_received",
    detail: "Interpret inbound intent and route to qualify, clarify, nurture, schedule, or escalate.",
  },
  {
    id: "book",
    title: "Book + Sync",
    state: "scheduling -> booked",
    detail: "Confirm slot, create booking, and sync stage/events back to CRM.",
  },
];

const PILLARS = ["Evidence grounded", "Policy enforced", "Traceable actions"];

export function LandingContent() {
  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <section className="relative overflow-hidden rounded-3xl border border-border/60 bg-surface px-6 py-10 shadow-sm md:px-10">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-cyan-300/25 blur-3xl dark:bg-cyan-400/15" />
        <div className="pointer-events-none absolute -bottom-16 left-8 h-60 w-60 rounded-full bg-primary/25 blur-3xl dark:bg-primary/20" />
        <div className="relative space-y-7">
          <p className="stage-reveal font-mono text-xs uppercase tracking-[0.24em] text-primary" style={{ animationDelay: "40ms" }}>
            Tenacious Ops
          </p>
          <div className="stage-reveal space-y-3" style={{ animationDelay: "120ms" }}>
            <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
              From signal research to booked calls.
            </h1>
            <p className="max-w-2xl text-base text-muted md:text-lg">
              One orchestration surface for lead intake, outreach, reply handling, and scheduling.
            </p>
          </div>
          <div className="stage-reveal flex flex-wrap items-center gap-3" style={{ animationDelay: "200ms" }}>
            <Link
              href="/pipeline"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all duration-300 hover:-translate-y-0.5 hover:opacity-90"
            >
              Open Pipeline
            </Link>
            <Link
              href="/runs"
              className="rounded-lg border border-border bg-background/70 px-4 py-2 text-sm font-semibold text-foreground transition-all duration-300 hover:-translate-y-0.5 hover:bg-background"
            >
              View Runs
            </Link>
          </div>
          <div className="stage-reveal flex flex-wrap gap-2" style={{ animationDelay: "280ms" }}>
            {PILLARS.map((pill) => (
              <span
                key={pill}
                className="rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs font-medium text-foreground"
              >
                {pill}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-border/60 bg-surface px-4 py-7 shadow-sm md:px-7">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">Interactive Workflow</h2>
            <p className="text-sm text-muted">Hover each stage to inspect what the engine does there.</p>
          </div>
          <p className="rounded-full border border-border/70 bg-background/70 px-3 py-1 font-mono text-xs text-muted">
            spec-aligned state transitions
          </p>
        </div>

        <div className="overflow-x-auto pb-24">
          <div className="relative mx-auto flex min-w-[980px] items-start justify-between px-6">
            <div className="absolute left-20 right-20 top-9 h-px bg-gradient-to-r from-primary/20 via-primary/60 to-cyan-500/40" />
            {WORKFLOW_STEPS.map((step, index) => (
              <div
                key={step.id}
                className="stage-reveal group relative flex w-32 shrink-0 flex-col items-center text-center"
                style={{ animationDelay: `${140 + index * 75}ms` }}
              >
                <button
                  type="button"
                  className="relative z-10 flex h-[72px] w-[72px] items-center justify-center rounded-2xl border border-primary/40 bg-background/90 text-sm font-semibold text-foreground shadow-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:scale-[1.03] group-hover:border-primary/70 group-hover:shadow-lg group-focus-visible:outline-none group-focus-visible:ring-2 group-focus-visible:ring-primary/60"
                  aria-label={`${step.title}: ${step.detail}`}
                >
                  {String(index + 1).padStart(2, "0")}
                </button>
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-foreground/90">{step.title}</p>

                <div className="pointer-events-none absolute left-1/2 top-28 z-20 w-60 -translate-x-1/2 translate-y-1 rounded-2xl border border-border/80 bg-surface/95 p-3 text-left opacity-0 shadow-xl backdrop-blur transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100">
                  <p className="font-mono text-xs font-semibold text-primary">{step.state}</p>
                  <p className="mt-2 text-xs leading-relaxed text-muted">{step.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
