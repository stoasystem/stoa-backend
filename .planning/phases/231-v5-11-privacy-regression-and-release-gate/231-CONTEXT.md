# Phase 231: v5.11 Privacy Regression And Release Gate - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Close v5.11 by verifying multi-action usage ledger coverage, privacy boundaries, account operations compatibility, documentation, and next milestone recommendations.

</domain>

<decisions>
## Implementation Decisions

### Release Gate Scope
- Run focused backend tests covering usage ledger, question quota compatibility, chat/teacher-help, practice/generation, reconciliation, and account operations.
- Run Ruff on changed backend and test files.
- Record adaptive full-suite date-sensitive residual risk separately instead of blocking on unrelated stale fixture assumptions.

### Privacy Boundary
- Verify no ledger tests store raw prompts, answers, hint text, teacher-help text, provider payloads, tokens, verification codes, or private artifact keys.
- Keep evidence in phase artifacts and milestone audit.

### Completion
- Mark v5.11 complete as a local backend release gate.
- Defer destructive cleanup/phase directory archiving because prior cleanup discovery showed stale archive path risk.

### the agent's Discretion
The agent may update planning files directly as long as all phase and requirement traceability remains explicit.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 227-230 SUMMARY/VERIFICATION artifacts.
- `roadmap.analyze` phase completion detection.
- Existing milestone snapshot files for v5.11 requirements and roadmap.

### Established Patterns
- Completed recent milestones record release state and known deferred items in `MILESTONES.md`, `PROJECT.md`, and `NEXT-MILESTONES.md`.

### Integration Points
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- `.planning/MILESTONES.md`
- `.planning/PROJECT.md`
- `.planning/NEXT-MILESTONES.md`

</code_context>

<specifics>
## Specific Ideas

- Close v5.11 as `multi-action-usage-ledger-ready`.
- Recommend v5.12 as product expansion selection rather than guessing the next build.

</specifics>

<deferred>
## Deferred Ideas

- Frontend display polish for multi-action usage summaries.
- Production deploy/live smoke.
- Cleanup archive migration until phase archive path is verified.

</deferred>
