# Phase 177 Rich Editor UI And API Readiness

## Status

Accepted as editor/API readiness handoff.

Phase 177 confirms STOA has a backend authoring lifecycle baseline and defines the frontend/editor contract required to turn it into a rich curriculum operations tool.

## Current Backend Readiness Baseline

| Capability | Current Endpoint/Service | Readiness |
|------------|--------------------------|-----------|
| Worklist | `GET /admin/curriculum/worklist` | Existing backend baseline. |
| Draft create | `POST /admin/curriculum/lessons/drafts` | Existing MVP baseline. |
| Preview | `GET /admin/curriculum/lessons/{public_lesson_id}/preview?versionId=...` | Existing backend baseline. |
| Submit review | `POST /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/submit-review` | Existing backend baseline. |
| Approve | `POST /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/approve` | Existing backend baseline. |
| Request changes | `POST /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/request-changes` | Existing backend baseline. |
| Publish | `POST /admin/curriculum/lessons/{public_lesson_id}/publish` | Existing compare-and-set manifest baseline. |
| Rollback | `POST /admin/curriculum/lessons/{public_lesson_id}/rollback` | Existing pointer rollback baseline. |
| Archive | `POST /admin/curriculum/lessons/{public_lesson_id}/archive` | Existing active-assignment refusal baseline. |
| Quality analytics | `GET /admin/curriculum/analytics/content-quality` | Existing aggregate-only analytics baseline. |

## Rich Editor Content Model Handoff

The frontend editor should model a lesson bundle as:

- Lesson metadata: public lesson ID, title, objective, description, subject, topic, unit, grade level, difficulty, locale/language, estimated duration.
- Rich sections: introduction, worked examples, formulas, code blocks, glossary terms, media references, common mistakes, practice guidance.
- Exercise blocks: prompt, type, choices, answer key, hints, explanation, difficulty, skills/tags, prerequisites, order, estimated duration.
- Review metadata: state, review state, updated by/at, review note, validation errors, publish readiness.
- Version metadata: public ID, version ID, current published version ID, manifest ID, rollback candidate IDs.

Current backend payloads already cover the MVP subset: lesson metadata, exercises, answer key, explanation, difficulty, order, skills, lifecycle state, manifests, and audit. Rich sections, media references, formulas, code blocks, prerequisites, diff payloads, and richer validation objects remain follow-up implementation fields.

## Frontend Handoff

Expected screens:

1. Curriculum worklist with filters by status, subject, topic, reviewer, and updated time.
2. Draft editor with block-level editing for lesson and exercises.
3. Preview tab using backend preview and published route shapes.
4. Diff tab comparing draft/review/published/rollback candidates.
5. Review tab for submit review, approve, request changes, and review notes.
6. Publish tab with publish readiness, expected current published version, reason input, and refusal handling.
7. Audit tab with append-only lifecycle events when backend audit read exposure is added.

State handling:

- Loading, empty, validation failure, permission denied, stale pointer, active assignment archive refusal, publish success, rollback success, and archive success must be visible.
- No hidden demo fallback for lifecycle mutation or validation state.
- Student/parent published routes remain the source of truth for learner-facing preview checks.

## Backend Follow-Up Tasks

- Add draft update/patch endpoint if frontend needs editing after initial draft create.
- Add structured validation endpoint or validation preview response if frontend needs pre-submit validation without state transition.
- Add diff endpoint or define frontend diff computation over preview payloads.
- Add read-only curriculum audit endpoint if audit tab needs event history.
- Expand `CurriculumLessonDraftRequest` and `curriculum_ops_service` payload normalization for rich sections, formulas, code blocks, media references, prerequisites, tags, and duration at exercise-block granularity.
- Add tests for each new rich field and for student/parent published-read stability.

## Published Read Stability

Student and parent reads remain governed by:

- `GET /practice/curriculum/catalog`
- `GET /practice/curriculum/lessons/{lesson_id}`
- `GET /practice/curriculum/exercises`
- `GET /practice/curriculum/progress`

Drafts, answer keys, review notes, and migration metadata must not appear in these responses unless a future approved contract explicitly changes visibility.

## Acceptance Mapping

| CURRICULUMXP-02 Criterion | Status |
|---------------------------|--------|
| Rich editor handoff covers lesson sections, formulas, media references, exercise blocks, answer keys, hints, explanations, tags, prerequisites, and duration. | Satisfied by content model handoff. |
| Backend API readiness covers draft update, preview, validation, submit review, approve/request changes, publish, rollback, archive, and audit behavior. | Existing baseline plus follow-up API gaps documented. |
| Frontend handoff identifies editor layout, review queue, diff/preview, and validation error implementation points. | Satisfied by UI-SPEC and frontend handoff. |
| Existing published-only student/parent reads remain stable while authoring drafts evolve. | Satisfied by published read stability section. |
| Focused checks cover route contract stability and content validation behavior when backend changes are needed. | Existing test targets named; no backend behavior changed in this phase. |

## Release Classification

Phase 177 is `editor-ready` as a handoff contract. It is not a completed frontend implementation.
