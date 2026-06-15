# Phase 183: Assignment Outcome Feedback Loop - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Make assignment lifecycle outcomes feed sequencing and analytics consistently. This phase records bounded start/complete/skip/archive feedback, keeps repeated completion idempotent, and exposes useful parent/tutor sequencing explanations without raw answers or internal ranking internals.

</domain>

<decisions>
## Implementation Decisions

### Feedback Recording
- Store compact `sequencing_feedback` metadata on assignments during lifecycle transitions.
- Include event, correctness, attempts, source type/source ID, subject, topic IDs, remediation topic IDs, and ranking effect.
- Do not store raw student answers in feedback metadata.
- Preserve repeated completion idempotency.

### Analytics
- Extend bounded curriculum analytics signals for assignment started and archived events.
- Keep existing assignment completed/skipped analytics behavior.
- Use hashed student metadata and aggregate-safe fields only.
- Record AI draft assignment signals by source ID when no curriculum exercise/lesson target exists.

### Response Shape
- Add a compact `sequencingSummary` to memory, recommendation, and parent progress responses.
- Explain active, completed, skipped, and archived assignment influence at a role-safe level.
- Do not expose raw scoring internals.

### the agent's Discretion
Keep implementation local to existing adaptive learning and curriculum analytics services. Avoid new tables or route families in this phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `transition_assignment` already centralizes assignment lifecycle behavior.
- `curriculum_analytics_service` already records completed and skipped assignment signals.
- Phase 182 recommendation source signals already consider assignment statuses for ranking.

### Established Patterns
- Assignment response fields use camelCase externally while storage remains snake_case.
- Analytics metadata avoids raw answers and uses stable hashed student identifiers.
- Completion side effects run only when transitioning from a non-completed state.

### Integration Points
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `tests/test_adaptive_learning.py`
- `tests/test_curriculum_analytics.py`

</code_context>

<specifics>
## Specific Ideas

Use lifecycle-specific ranking effects: `active_assignment_suppresses_duplicates`, `completion_reduces_exact_source_priority`, `skip_temporarily_reduces_priority`, and `archive_suppresses_exact_source`.

</specifics>

<deferred>
## Deferred Ideas

Warehouse export and operator dashboard aggregation of these signals belongs to Phase 184.

</deferred>
