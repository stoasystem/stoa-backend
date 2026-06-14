# Phase 177 Context: Admin Rich Curriculum Editor UI And API Readiness

## Why This Phase Exists

v4.6 added backend curriculum authoring, publish, rollback, archive, and analytics foundations. v5.1 Phase 176 accepted the richer editor and migration contract. Phase 177 turns that contract into an implementation handoff for the admin/tutor curriculum editor surface and confirms the existing backend API readiness boundaries.

## Phase Boundary

This phase defines editor UX/API readiness and handoff. It does not build the full frontend editor in `/Users/zhdeng/stoa-frontend`, migrate production content, or alter published student/parent curriculum reads.

## Implementation Decisions

### Editor Scope

- Treat the editor as an operations tool for admin/tutor/teacher roles, not a student-facing authoring surface.
- Preserve the current backend lifecycle: draft, preview, submit review, approve, request changes, publish, rollback, archive, worklist, audit, and aggregate analytics.
- Include rich content fields in the handoff even when the current backend accepts only the v4.6 MVP field subset; unsupported fields become frontend/backend follow-up tasks.

### UI Approach

- Use a dense operational editor layout with left navigation/worklist, center content editor, right validation/review panel, and preview/diff tabs.
- Prefer explicit validation messages and refusal reasons over silent fallback.
- Keep answer keys, draft-only metadata, and review notes out of student/parent preview routes.

### Backend Compatibility

- Existing admin routes under `/admin/curriculum/*` are the readiness baseline.
- Existing published routes under `/practice/curriculum/*` remain published-only for students/parents.
- Any future rich-field expansion must preserve canonical public IDs, version IDs, publish manifests, compare-and-set pointer behavior, and append-only audit evidence.

## Existing Code Insights

### Reusable Assets

- `src/stoa/routers/admin.py` exposes worklist, draft create, preview, submit review, approve, request changes, publish, rollback, archive, and content-quality endpoints.
- `src/stoa/services/curriculum_ops_service.py` owns authoring lifecycle, validation, manifests, rollback, archive guards, and audit events.
- `src/stoa/services/curriculum_service.py` owns published catalog, lesson, exercise, and progress projections.
- `src/stoa/services/curriculum_analytics_service.py` owns aggregate content-quality signals.

### Established Patterns

- Authoring mutations are role-gated and explicit.
- Publish/rollback uses expected published-version compare-and-set semantics.
- Archive refuses active assignment references.
- Student/parent curriculum reads exclude drafts and answer keys by default.

### Integration Points

- `/Users/zhdeng/stoa-frontend` should implement the editor UI against the admin route surface.
- Backend rich-field expansion should happen in `CurriculumLessonDraftRequest`, `curriculum_ops_service._lesson_payload`, `_exercise_payloads`, and validation.
- Tests should extend `tests/test_curriculum_ops.py`, `tests/test_curriculum_rollout.py`, and frontend editor e2e coverage when implementation starts.

## Deferred Ideas

- Collaborative editing, autosave conflict resolution, embedded media upload pipeline, and formula rendering implementation remain future frontend/backend work.
- Production content import belongs to Phase 178.
- Assignment automation belongs to Phase 179.
