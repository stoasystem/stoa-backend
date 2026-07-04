# Phase 229: Practice And Generation Ledger Instrumentation - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Instrument eligible practice, hint, lesson, assignment, and reviewed generation flows with privacy-safe usage ledger events. This phase should avoid passive reads, failed attempts before persistence, previews, and drafts that are not accepted into a governed workflow.

</domain>

<decisions>
## Implementation Decisions

### Practice Coverage
- Record hint requests after the hint counter succeeds and a hint is returned.
- Record practice answers after attempt persistence.
- Record lesson completion after progress persistence.
- Do not record catalog reads, lesson detail reads, progress reads, or mistakes reads.

### Assignment And Generation Coverage
- Record reviewed assignment generation after manual or automation-created assignment persistence.
- Record assignment lifecycle events only for real side effects: started, completed, skipped, archived.
- Do not record automation previews, refused candidates, duplicate replays, or unsupported sources.
- Do not store assignment prompts, answer keys, student answers, notes, or rationales in ledger metadata.

### Failure Behavior
- Practice/adaptive support-visible ledger write failures should not break the learning action after the main persistence succeeds.
- Existing quota counters remain authoritative for hints.

### the agent's Discretion
Use small local helpers in route/service modules for bounded metadata and failure isolation.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `usage_ledger_service.record_usage_event` from Phase 228.
- `rate_limit.check_and_record_hint` now returns counter metadata.
- Practice routes already have successful persistence points for answers and lessons.
- Adaptive service has assignment creation and transition side-effect points.

### Established Patterns
- Practice analytics already avoids raw answers through hashing/signals.
- Adaptive responses hide answer keys and student answers from parents.
- Automation duplicate/refusal paths return structured results without persistence.

### Integration Points
- `src/stoa/routers/practice.py`
- `src/stoa/services/adaptive_learning_service.py`
- `tests/test_curriculum_analytics.py`
- `tests/test_adaptive_learning.py`

</code_context>

<specifics>
## Specific Ideas

- Record only resource IDs and classification metadata.
- Catch support-visible ledger write exceptions after primary persistence.

</specifics>

<deferred>
## Deferred Ideas

- Multi-action reconciliation and summary aggregation remain Phase 230.

</deferred>
