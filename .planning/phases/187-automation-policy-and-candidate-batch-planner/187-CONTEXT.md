# Phase 187: Automation Policy And Candidate Batch Planner - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement a preview-only controlled assignment automation planner. This phase turns existing v5.2 sequencing recommendations into tutor/admin-reviewable candidate batches under an explicit policy. It must not create assignments or deliver work to students.

</domain>

<decisions>
## Implementation Decisions

### Policy Scope
- Support per-student preview policies with `policyId`, status, automation level, allowed source types, subject/topic filters, confidence threshold, freshness window, max assignment count, due-window default, and delivery mode.
- Treat `off` and `paused` as refusal-producing states rather than errors so operators can see what would have been selected.
- Default to reviewed assignment-capable sources: accepted AI drafts and published curriculum exercises.
- Preserve future unattended delivery as deferred scope.

### Candidate Selection
- Reuse `get_memory_summary()` and v5.2 recommendation output instead of duplicating ranking logic.
- Select recommendations only after policy filtering; return all other candidates as refused with concrete refusal codes.
- Keep selected/refused response shape stable for future tutor/admin review UI.
- Never write assignments in the preview phase.

### Safety Boundaries
- Require tutor/teacher/admin access.
- Preserve `reviewRequired: true` and `autonomousDecision: false` at batch level and candidate level.
- Do not expose answer keys, raw student answers, or internal score values.
- Use current assignment state to refuse duplicates and active exact-source/topic work.

### the agent's Discretion
- Use existing helper patterns inside `adaptive_learning_service.py` rather than adding a new repository or persisted policy table in this phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `adaptive_learning_service.get_memory_summary()` already builds recommendations, sequencing summaries, and role-scoped visibility.
- `_assignment_signal_state()` already captures active topics and suppressed sources for duplicate handling.
- Existing assignment routes in `src/stoa/routers/adaptive.py` use Pydantic request models with camelCase aliases.

### Established Patterns
- Tutor/admin-only assignment workflows use `require_role("teacher", "tutor", "admin")`.
- Adaptive responses include `locale`, `reviewRequired`, and `autonomousDecision` fields when surfacing recommendation-like data.
- Tests monkeypatch repository functions directly for focused backend behavior.

### Integration Points
- Add preview endpoint under `/adaptive/students/{student_id}/assignment-automation/batches/preview`.
- Add service function in `adaptive_learning_service.py`.
- Add focused coverage to `tests/test_adaptive_learning.py`.

</code_context>

<specifics>
## Specific Ideas

The planner should return `selected`, `refused`, and `summary` sections so Phase 188 can consume approved selected candidates without changing the preview contract.

</specifics>

<deferred>
## Deferred Ideas

- Persisting automation policies.
- Persisting preview batches.
- Assignment creation from approved batches.
- Student-visible delivery changes.

</deferred>
