# Phase 179 Assignment Automation And Adaptive Sequencing Readiness

## Status

Accepted as assignment/sequencing readiness handoff.

Phase 179 defines how STOA should move from reviewed manual assignments toward controlled automation and future adaptive sequencing.

## Current Baseline

| Area | Current Capability |
|------|--------------------|
| Memory | Adaptive learning memory summarizes questions, mistakes, profile signals, snapshots, and next-practice recommendations. |
| Assignments | Tutors/admins can create reviewed assignments from curriculum exercises or accepted AI drafts. |
| Lifecycle | Assignments support draft, recommended, assigned, started, completed, skipped, and archived states. |
| Progress | Completion records practice progress and content-quality signals. |
| Analytics | Aggregate curriculum quality metrics include wrong answers, assignment skips, completions, publish, and archive signals. |
| Safety | Curriculum archive refuses active assignment references. |

## Assignment Eligibility

Eligible sources:

- Published curriculum exercises with stable public IDs.
- Accepted AI drafts that have passed tutor/admin review.
- Future migrated content only after apply evidence exists and publish/readiness rules pass.

Ineligible sources:

- Draft curriculum versions.
- In-review or changes-requested versions.
- Archived or rolled-back content that is not the current published pointer.
- Generated exercises that have not been reviewed.
- Content with active validation blockers or missing answer key/explanation.

## Automation Lifecycle

| State | Meaning | Actor |
|-------|---------|-------|
| Candidate | System identifies eligible source for a student. | System |
| Recommended | Candidate is visible as suggested practice but not required. | System or tutor/admin |
| Assigned | Tutor/admin or approved automation assigns work. | Tutor/admin or controlled automation |
| Started | Student starts work. | Student |
| Completed | Student submits work; progress and analytics are recorded. | Student |
| Skipped | Student skips or tutor/admin suppresses work; skip signal is recorded. | Student or tutor/admin |
| Archived | Assignment is no longer active; historical signals remain. | Tutor/admin |

Default v5.1 posture: automation may produce candidates/recommendations, while assignment remains review-gated unless a future release explicitly enables controlled auto-assign.

## Duplicate Prevention

Do not recommend or assign a source when:

- The student already has an active assignment for the same exercise or lesson.
- The student recently completed the same source inside the stale-window policy.
- The content version is no longer current and no historical in-progress assignment requires it.
- The source was skipped repeatedly and no tutor/admin override exists.
- The source belongs to archived/rollback-disabled content.

Recommended deterministic key:

`student_id + source_type + source_id + version_id`

## Sequencing Signal Model

Candidate generation may use:

- Curriculum progress by subject/topic/lesson.
- Mistake counts and weak topic counters.
- Adaptive memory snapshots.
- Assignment outcomes: completed, skipped, correct/incorrect.
- AI draft outcomes and tutor acceptance/rejection state.
- Content-quality metrics: wrong answers, skips, completions, publish/archive events.
- Prerequisite lesson completion.
- Tutor/admin override or priority tags.

Ranking should start deterministic:

1. Exclude ineligible/stale/duplicate content.
2. Prioritize unmet prerequisites and weak topics.
3. Prefer reviewed/published content with stable quality.
4. Down-rank high-skip or recently failed content unless tutor/admin override exists.
5. Produce rationale fields for tutor/admin review.

## Visibility Rules

| Role | Visibility |
|------|------------|
| Student | Assigned/recommended work, status, due date, safe rationale, own progress. |
| Parent | Linked child progress, assigned/completed counts, weak areas, recommendations; no answer keys or draft metadata. |
| Tutor/teacher | Candidate rationale, assignment source, review state, override controls, student progress. |
| Admin | All tutor fields plus content quality, migration/source evidence, and rollout controls. |

## Backend Implementation Targets

Future implementation should add:

- Candidate generation service that returns non-mutating recommendations.
- Eligibility helper that centralizes published/reviewed/archived/rollback checks.
- Duplicate prevention keyed by student/source/version.
- Rationale payload for tutor/admin review.
- Optional candidate-to-assignment action with explicit operator approval.
- Tests covering candidate exclusion, duplicate prevention, archived content, reviewed AI draft gating, and analytics signal propagation.

## Test Targets

- Reviewed curriculum exercise can become candidate.
- Unreviewed AI draft cannot become candidate.
- Accepted AI draft can become candidate but remains review-visible.
- Existing active assignment suppresses duplicate candidate.
- Archived/rolled-back content is excluded from new candidates.
- Assignment completion and skip continue to record aggregate analytics.
- Parent/student visibility omits answer keys and draft metadata.

## Acceptance Mapping

| CURRICULUMXP-04 Criterion | Status |
|---------------------------|--------|
| Assignment automation readiness defines when reviewed/generated exercises may be proposed, assigned, skipped, completed, or archived. | Satisfied by eligibility and lifecycle sections. |
| Sequencing signals use curriculum progress, mistakes, AI draft outcomes, assignment outcomes, analytics, and tutor review state. | Satisfied by sequencing signal model. |
| Student/parent/tutor visibility boundaries are documented. | Satisfied by visibility rules. |
| Automation remains review-gated where required. | Satisfied by default v5.1 posture and ineligible source rules. |
| Tests/checks cover assignment eligibility, duplicate prevention, progression signals, and archived/rolled-back content behavior. | Test targets defined; implementation deferred. |

## Release Classification

Phase 179 is `assignment-ready` as a readiness contract. It does not enable fully autonomous assignment publication.
