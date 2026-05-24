# ADR Format

Architecture Decision Records (ADRs) capture *why* a decision was made — not just what was decided. They age remarkably well and save enormous amounts of re-deliberation.

---

## Format

Each ADR is a short markdown file. If using a flat `DECISIONS.md`, separate records with `---`. If using an `adr/` folder, name files `adr/NNN-short-title.md` (e.g., `adr/001-use-zustand-for-client-state.md`).

```markdown
# ADR-[NNN]: [Short Title]

**Status:** [Proposed | Accepted | Deprecated | Superseded by ADR-NNN]  
**Date:** YYYY-MM-DD  
**Deciders:** [Names or team]

## Context

[1-3 paragraphs describing the situation, constraints, and forces at play that led to this decision. What problem needed solving? What were the constraints? Why did it come up now?]

## Decision

[State the decision clearly in 1-2 sentences. Start with "We will..." or "We have decided to..."]

## Alternatives Considered

### [Option A]
[Brief description]  
**Pros:** [...]  
**Cons:** [...]

### [Option B]
[Brief description]  
**Pros:** [...]  
**Cons:** [...]

## Consequences

**Positive:**
- [Expected benefit]
- [Expected benefit]

**Negative / Tradeoffs:**
- [Accepted downside]
- [Accepted downside]

**Risks:**
- [Known risk and mitigation if any]
```

---

## Status Lifecycle

- **Proposed** — under discussion, not yet committed
- **Accepted** — decided and in effect
- **Deprecated** — was accepted, no longer applies (system changed, etc.)
- **Superseded** — replaced by a newer ADR; link to it

---

## Example

```markdown
# ADR-001: Use Zustand for Client State Management

**Status:** Accepted  
**Date:** 2024-03-12  
**Deciders:** Frontend platform team

## Context

As the app grew, we needed a consistent approach to client-side state. We were mixing React Context, prop drilling, and ad-hoc useState in ways that made cross-component state sharing brittle. We needed something lightweight that the whole team could agree on.

## Decision

We will use Zustand for all client-side global state. Server state (API data) continues to live in TanStack Query.

## Alternatives Considered

### Redux Toolkit
Well-established, excellent devtools, great for large teams.  
**Pros:** Industry standard, strong TypeScript support, time-travel debugging  
**Cons:** Significant boilerplate, overkill for our scale, slower onboarding

### React Context + useReducer
No additional dependency, built into React.  
**Pros:** Zero bundle cost, no new concepts  
**Cons:** Causes unnecessary re-renders, awkward to split into domains, no devtools

### Jotai
Atomic model, tiny bundle.  
**Pros:** Very flexible, excellent performance  
**Cons:** Less familiar to the team, atomic model requires more upfront design

## Consequences

**Positive:**
- Minimal boilerplate — stores are simple functions
- Excellent TypeScript inference out of the box
- Easy to split by domain without ceremony
- Works cleanly alongside TanStack Query

**Negative / Tradeoffs:**
- Less structured than Redux — discipline required to avoid stores becoming grab-bags
- Devtools less mature than Redux DevTools

**Risks:**
- Risk of overusing stores for things that should be local state — mitigated by the server/client state split documented in STATE_MANAGEMENT.md
```
