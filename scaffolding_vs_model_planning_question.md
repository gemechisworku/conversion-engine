# Research Brief: Scaffolding-Driven vs Model-Driven Planning

## Selected Question

In multi-turn agent systems that combine deterministic orchestration (state machines, routers, policy gates) with LLM judgment, how should we characterize which planning decisions belong to scaffolding versus the model, and where does that boundary become most brittle under ambiguous user inputs?

## Why This Question Is Valuable

This is a recurring architecture problem across FDE work: systems need deterministic control for safety and reliability, but also adaptive reasoning for messy, ambiguous user language.
Most production failures in agentic systems come from the boundary between these two layers, not from either layer in isolation.

## Scope (Generalized)

### In Scope

- Multi-turn agent architectures with:
  - deterministic control flow,
  - model-mediated interpretation,
  - downstream actions that have business or product consequences.
- Ambiguity handling under realistic user inputs (mixed intent, incomplete information, conflicting cues).
- Failure analysis of planning ownership and handoff points.

### Out of Scope

- Provider-specific API details.
- UI rendering details.
- Project-specific implementation quirks that do not generalize.

## Conceptual Frame

- **Scaffolding layer**: explicit transitions, deterministic routing, policy constraints, retries, and execution order.
- **Model layer**: semantic interpretation, ambiguity resolution, and context-sensitive judgment.
- **Boundary layer**: conversion of model outputs into deterministic actions.

The core diagnostic question is whether the architecture assigns each planning decision to the layer best suited to handle its uncertainty.

## What a Strong Answer Should Cover

### 1) Decision Ownership Model

Define a clear, portable model of planning ownership:

- which decisions are strictly deterministic,
- which decisions are probabilistic/model-mediated,
- which decisions are hybrid and require arbitration.

A strong answer should make this operational (for example: decision classes, ownership rules, and expected confidence posture per class).

### 2) Ambiguity Typology

Identify at least three ambiguity classes that commonly break agent planners, such as:

- mixed intent in one user turn,
- underspecified requests that require clarification,
- lexical cues that look actionable but are contextually non-committal.

For each class, explain how it can be misinterpreted by deterministic routing and by model reasoning.

### 3) Failure Path Anatomy

Walk through how a single ambiguous input becomes a wrong downstream action:

1. interpretation step,
2. routing/decision step,
3. state update step,
4. action execution step.

A strong answer should pinpoint where correctness is lost and why later safeguards fail to recover it.

### 4) Boundary Brittleness Analysis

Explain why brittle behavior tends to cluster at handoff points between model output and deterministic execution, including:

- premature commitment to a branch,
- skipped or conditional model refinement,
- syntactically valid but semantically wrong state progression.

The explanation should distinguish between "allowed by workflow" and "correct for user intent."

### 5) Failure Attribution Framework

Separate failure causes into:

- **Scaffolding failures**: rigid control flow, poor transition design, inadequate uncertainty representation.
- **Model failures**: semantic misreads, instability under ambiguity, overconfident interpretation.
- **Interface failures**: lossy context transfer, weak confidence semantics, brittle output-to-action mapping.

A strong answer should show how these interact rather than treating them as isolated buckets.

### 6) Generalizable Architectural Insights

Conclude with portable insights any FDE can apply when evaluating hybrid agent systems, such as:

- what kinds of decisions should never be purely heuristic,
- what kinds should never be purely model-driven,
- what signals indicate the architecture is over-indexed on one side.

## Expected Explanation Depth

Target a **600-1,000 word explainer** that is:

- **Mechanistic**: describes decision flow step-by-step.
- **Architectural**: uses system-level concepts rather than project-local details.
- **Diagnostic**: identifies concrete brittleness points and causal chains.
- **Generalizable**: useful to teams building different products with similar hybrid agent patterns.

Minimum bar for completeness:

- one clear ownership model,
- three ambiguity classes with walkthroughs,
- one failure-attribution framework,
- one synthesis section with transferable conclusions.

## Suggested Deliverable Structure

1. Problem framing: hybrid planning in agent systems
2. Ownership model: scaffolding vs model vs boundary
3. Ambiguity classes and failure walkthroughs
4. Boundary brittleness and causal analysis
5. General lessons for FDE architecture decisions
