# Phase 181 Adaptive Sequencing And Warehouse Analytics Contract

## Scope

v5.2 expands STOA's adaptive learning foundation into richer sequencing and analytics readiness. The milestone should implement or define multi-signal next-work recommendations, assignment outcome feedback, warehouse-ready exports, and operator dashboards.

## Ownership Boundaries

| Area | Owner | v5.2 Responsibility |
|------|-------|---------------------|
| Adaptive backend | `stoa-backend` | Candidate generation, ranking, dedupe, assignment feedback, role-visible responses |
| Curriculum/backend analytics | `stoa-backend` | Content-quality metrics, assignment outcome signals, export schemas |
| Frontend UX | `/Users/zhdeng/stoa-frontend` | Student/tutor recommendation views, admin dashboard integration, explanation rendering |
| Tutor/curriculum owner | Product/curriculum team | Review gates, assignment acceptance, intervention workflow |
| Data/warehouse | Future analytics owner | Warehouse schemas, scheduled export, BI dashboards |

## Sequencing Inputs

Sequencing may use:

- Latest memory snapshots by student/subject/topic.
- Curriculum progress and lesson completion.
- Practice mistakes and challenge attempts.
- Reviewed AI draft availability and accepted/rejected outcomes.
- Assignment status and outcome history.
- Curriculum content-quality metrics and stale content markers.
- Tutor/admin review state and intervention notes.

## Candidate And Ranking Contract

Candidate types:

- `curriculum_exercise`
- `reviewed_ai_draft`
- `remediation_topic`
- `continuation_lesson`
- `tutor_intervention`

Ranking outputs:

- Stable candidate ID and source type.
- Rationale suitable for student/tutor display.
- Confidence bucket.
- Freshness timestamp/source.
- Source signal summary.
- `reviewRequired` and `autonomousDecision=false` by default.

Suppression rules:

- Suppress duplicates when active assignments already cover the same source/topic.
- Suppress unpublished, archived, rolled-back, or inactive curriculum content.
- Avoid immediate repeat after skipped work unless remediation pressure remains high.
- Do not auto-assign generated content without review.

## Assignment Feedback Contract

Assignment events should update sequencing and analytics:

- `started`
- `completed`
- `skipped`
- `archived`
- `remediation_recommended`

Completion should capture correctness, attempts, topic/subject, source content, and remediation signal. Skip/archive should reduce priority temporarily, not permanently remove useful remediation.

## Warehouse Analytics Contract

Warehouse-ready schemas should cover:

- Learning memory snapshots.
- Recommendation candidates and ranking decisions.
- Assignment lifecycle outcomes.
- Curriculum progress and content-quality metrics.
- Cohort/subject/topic aggregates.
- Intervention opportunities and stale content indicators.

Live warehouse deployment is not required in v5.2 unless selected later; local export/readiness contracts and backend-shaped responses are sufficient for internal development.

## Rollout States

- `contract-ready`: sequencing/analytics contract and handoff docs are complete.
- `sequencing-ready`: recommendation generation and ranking behavior are implemented or verified.
- `analytics-ready`: assignment feedback and operator analytics are verified.
- `warehouse-ready`: export schemas and readiness checks are verified.
- `blocked`: missing data, frontend, or analytics ownership blocks rollout.
- `deferred`: local readiness is complete but live warehouse/BI remains future scope.

## Implementation Handoff

Phase 182 should implement adaptive sequencing recommendation behavior.

Phase 183 should implement assignment outcome feedback loop behavior.

Phase 184 should implement warehouse analytics export/readiness and operator dashboards.

Phase 185 should verify v5.2, record rollout state, and update the remaining-feature queue.
