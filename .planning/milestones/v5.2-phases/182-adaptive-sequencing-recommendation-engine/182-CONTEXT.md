# Phase 182: Adaptive Sequencing Recommendation Engine - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement a multi-signal adaptive sequencing recommendation engine inside the existing adaptive learning backend. The phase enriches recommendation generation, ranking, dedupe, freshness, rationale, and role-visible response shape, but it does not auto-create assignments or enable autonomous tutoring.

</domain>

<decisions>
## Implementation Decisions

### Recommendation Contract
- Preserve the existing `/adaptive/students/{student_id}/recommendations` and memory summary entry points.
- Keep every recommendation `reviewRequired: true` and `autonomousDecision: false`.
- Expose stable candidate IDs, candidate/source type, confidence bucket, freshness, rationale, source signals, and review flags.
- Keep rationale useful for students/tutors without exposing raw internal scoring internals.

### Candidate Sources
- Generate curriculum exercise candidates from active published curriculum/practice content.
- Generate reviewed AI draft candidates only from accepted practice exercise drafts for the same student.
- Generate remediation topic candidates from weak topics, mistakes, and memory snapshots.
- Generate continuation lesson candidates only as low-risk maintenance/freshness follow-up when stronger remediation is absent.

### Dedupe And Suppression
- Suppress active assignment duplicates by topic and exact source.
- Suppress completed, archived, rolled-back, unpublished, or inactive exact-source recommendations.
- Treat skipped work as a temporary priority reduction rather than permanent suppression.
- Preserve existing assignment lifecycle and idempotency behavior.

### the agent's Discretion
Use codebase-local deterministic scoring and existing repository/service helpers. Avoid new storage tables in this phase unless required by tests.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/adaptive_learning_service.py` already builds memory snapshots, parent-safe memory responses, assignments, and `_next_practice_recommendations`.
- `curriculum_service.list_exercises` filters active/published exercise projections and hides preview content by default.
- `ai_teacher_tools_repo.list_drafts` can list accepted practice exercise drafts by student.
- `adaptive_learning_repo.list_assignments` provides assignment status/source/topic state for dedupe.

### Established Patterns
- Recommendation data is dict-shaped and returned through memory summary plus `/recommendations`.
- Adaptive outputs use camelCase externally and preserve locale metadata separately.
- Parent views redact raw evidence while still showing weak topics and recommendations.
- Tests monkeypatch repositories directly and verify role/locale/idempotency contracts.

### Integration Points
- Replace or extend `_next_practice_recommendations` in `adaptive_learning_service.py`.
- Add focused tests in `tests/test_adaptive_learning.py`.
- Keep router response shape stable while allowing enriched recommendation item fields.

</code_context>

<specifics>
## Specific Ideas

Use a small internal candidate builder/ranker instead of a new framework. Rank by weakness/mistake pressure, curriculum availability, reviewed draft availability, freshness, and assignment suppression state.

</specifics>

<deferred>
## Deferred Ideas

- Live warehouse export and dashboard work belongs to Phase 184.
- Assignment outcome signal persistence beyond existing analytics hooks belongs to Phase 183.
- Fully autonomous tutoring and unreviewed generated assignment remain out of scope.

</deferred>
