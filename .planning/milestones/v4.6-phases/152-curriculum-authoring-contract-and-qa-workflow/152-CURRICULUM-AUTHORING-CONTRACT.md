# Curriculum Authoring Contract

**Phase:** 152 - Curriculum Authoring Contract And QA Workflow
**Milestone:** v4.6
**Status:** Accepted

## Purpose

Phase 153 must add internal authoring without changing the public meaning of the existing curriculum catalog, lesson, exercise, progress, or adaptive-assignment APIs. This contract defines the identity, lifecycle, validation, publish, archive, rollback, and role rules that implementation must preserve.

## Identity Model

Stable public identifiers are API identities. They are safe to store in progress rows, assignments, adaptive memory, analytics, and frontend URLs.

| Entity | Stable public ID | Immutable version ID | Notes |
|--------|------------------|----------------------|-------|
| Lesson | `lesson_id` | `lesson_version_id` | Public lesson ID survives edits and rollback. |
| Exercise | `exercise_id` / existing `challenge_id` | `exercise_version_id` | `challenge_id` remains accepted for compatibility; new code may expose `exercise_id` as the canonical public alias. |
| Publish manifest | `manifest_id` | immutable by definition | Captures the exact lesson/exercise version bundle used for a publish event. |
| Audit event | `event_id` | immutable by definition | Append-only evidence of user, action, transition, and reason. |

Required implementation rules:

- A public ID may point to only one published version at a time.
- Version IDs are never reused and are never mutated after publish, approval, archive, or rollback.
- Historical analytics and assignment records must store both public IDs and version IDs when the version is known.
- Existing progress and mistake rows that only know `lesson_id` / `challenge_id` remain valid.
- Authoring drafts may share a public ID target but must not replace published projections until a publish transaction succeeds.

## Storage Boundary

Phase 153 should add a dedicated curriculum operations repository/service layer instead of expanding `curriculum_service.py` into an authoring service.

Recommended same-table row families:

| Row family | Purpose |
|------------|---------|
| `CURRICULUM_VERSION#...` | Immutable lesson/exercise version snapshots. |
| `CURRICULUM_POINTER#...` | Mutable draft/review/published pointer by public ID. |
| `CURRICULUM_MANIFEST#...` | Publish bundle containing one lesson version and its exercise versions. |
| `CURRICULUM_AUDIT#...` | Append-only lifecycle/audit evidence. |
| `CURRICULUM_WORKLIST#...` | Optional operator queue projection for pending review/publish work. |
| Existing `PRACTICE` rows | Published projection consumed by current student/tutor routes. |

Student-facing reads continue to use existing published `PRACTICE` projections unless Phase 153 explicitly adapts `curriculum_service.py` to a published-only projection reader with equivalent behavior.

## Separate State Machines

Do not overload one generic `status` field across content, review, assignments, and AI drafts. Each state machine has a separate owner and refusal model.

### Content Version Lifecycle

| From | To | Actor | Required condition |
|------|----|-------|--------------------|
| `draft` | `in_review` | author/tutor/admin | Validation passes for review readiness. |
| `in_review` | `changes_requested` | reviewer/admin | Review records blocking issues. |
| `changes_requested` | `draft` | author/tutor/admin | Author resumes editing. |
| `in_review` | `approved` | reviewer/admin | Review passes and reviewer is not the sole author when separation is enforced. |
| `approved` | `published` | publisher/admin | Publish manifest is complete and compare-and-set pointer check passes. |
| `published` | `archived` | publisher/admin | Archive guard passes; active assignment/historical reference rules are satisfied. |
| `published` | `superseded` | publisher/admin | A newer version is published for the same public ID. |

Illegal transitions must return explicit refusal reasons, for example `validation_failed`, `not_approved`, `stale_pointer`, `active_assignments_block_archive`, or `student_visibility_forbidden`.

### QA Review Outcome Lifecycle

| State | Meaning |
|-------|---------|
| `pending` | Submitted and awaiting review. |
| `approved` | Ready for publish. |
| `changes_requested` | Not publishable until edited and resubmitted. |
| `withdrawn` | Author removed from review before decision. |

Review outcome is evidence about a version. It is not the same as content visibility.

### Assignment Lifecycle

Existing adaptive assignment states remain separate: `recommended`, `assigned`, `started`, `completed`, `skipped`, and `archived` keep their student ownership and role rules. Assignment transitions must not publish, approve, or archive curriculum content.

### AI Draft Acceptance Lifecycle

Existing AI draft states remain separate from curriculum content. `accepted` AI drafts can be assignment sources, but they are not published curriculum until a future authoring flow imports them into a curriculum version and passes QA/publish.

## Role Boundaries

| Role | Allowed curriculum operation |
|------|------------------------------|
| Author | Create/edit draft, submit review, withdraw review. |
| Reviewer | Approve or request changes; should not silently publish. |
| Publisher/admin | Publish, rollback, archive, repair pointers, view audit. |
| Tutor/teacher | Preview drafts/review content when authorized; create or submit drafts if Phase 153 includes tutor authoring. |
| Student | Read published projections only; update own assignment progress only. |
| Parent | Read published/progress projections for bound children only; no drafts, answer keys, or raw analytics. |

Preview must be opt-in and role-gated. The current `includePreview` pattern is acceptable for admin/tutor paths, but student/parent routes must not honor draft/review preview.

## Publish Unit And Manifest

A publish unit is a lesson-plus-exercises bundle. Publishing only a lesson shell without its required exercises is invalid unless the lesson is explicitly marked as non-practice/reference content.

Each manifest must include:

- `manifest_id`
- target `lesson_id`
- `lesson_version_id`
- ordered exercise public IDs and version IDs
- previous published pointer values
- requested actor, approved actor, published actor
- validation result hash or summary
- `published_at`
- rollback eligibility
- audit event IDs

Publish rules:

- Publish is conditional on the current published pointer matching the manifest's expected previous pointer.
- Publish updates the published projection atomically enough that readers never see a mixed lesson/exercise bundle.
- Re-running the same publish request is idempotent when the manifest is already current.
- Publishing a new version supersedes the prior published version but does not delete it.

Rollback rules:

- Rollback publishes a previous manifest as a new pointer transition.
- Rollback writes a new audit event and records the reason.
- Rollback does not mutate historical version snapshots.

Archive rules:

- Archive is a pointer/lifecycle transition, not hard deletion.
- Archive refuses when active assignments depend on the public ID unless a safe migration/repoint path is implemented.
- Archived content remains readable for historical internal/audit interpretation as needed.
- Student catalog reads exclude archived content unless an existing in-progress assignment requires a safe historical view.

## Validation Rules

Validation has levels: draft-save, submit-review, approve, and publish. Each later level includes the earlier checks.

Required checks before publish:

- Lesson title, objective/description, subject, topic, grade level, difficulty, estimated minutes, and language/locale metadata are present.
- Exercise prompt, type, difficulty, lesson binding, subject/topic binding, expected answer/answer key, and explanation/hints are present when required by type.
- Exercise order is deterministic and unique within the lesson publish unit.
- Subject IDs use existing aliases and supported values consistently with `curriculum_service.SUPPORTED_SUBJECTS`.
- `lesson_id` and `exercise_id` are stable, URL-safe, and do not collide with unrelated content.
- Answer keys are never returned to student/parent responses.
- Legacy v3.8 projection fields required by catalog, lesson detail, exercise list, progress, and assignment source reads can be produced.

## Visibility Contract

Published projections:

- `GET /practice/curriculum/catalog`
- `GET /practice/curriculum/lessons/{lesson_id}`
- `GET /practice/curriculum/exercises`
- `GET /practice/curriculum/progress`
- existing `/practice/lessons/{lesson_id}` and related practice routes
- adaptive assignment source lookup for `curriculum_exercise`

These routes must remain published-only for students and parents. Admin/tutor preview may use separate admin routes or existing preview parameters, but preview must not alter default published behavior.

## Audit Requirements

Every lifecycle mutation must write append-only audit evidence:

- actor ID and role
- operation name
- source state and target state
- public ID and version ID
- manifest ID when applicable
- refusal reason for denied transitions where useful
- timestamp
- request idempotency key when available

Audit records must not include raw student answers, answer keys in student-visible contexts, or hidden AI prompts.

## Phase 153 Handoff

Phase 153 implementation should prove:

- legal and illegal lifecycle transitions;
- draft isolation from student/parent reads;
- publish idempotency and stale-pointer refusal;
- rollback restores a prior manifest without mutating version rows;
- archive refuses unsafe active-assignment cases;
- audit events are created for mutation attempts;
- existing v3.8/v4.0 curriculum and adaptive tests keep passing.

