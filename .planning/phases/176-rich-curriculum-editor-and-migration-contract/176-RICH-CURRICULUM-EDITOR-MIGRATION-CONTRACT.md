# Phase 176 Rich Curriculum Editor And Migration Contract

## Scope

v5.1 expands STOA's curriculum foundations into product-ready operations. The milestone should prepare rich editor UX/API handoff, production content migration, validation/rollback evidence, assignment automation readiness, and adaptive sequencing readiness.

## Ownership Boundaries

| Area | Owner | v5.1 Responsibility |
|------|-------|---------------------|
| Backend curriculum APIs | `stoa-backend` | Draft/version lifecycle, validation, preview, publish/rollback/archive, migration evidence, assignment readiness |
| Frontend editor UX | `/Users/zhdeng/stoa-frontend` | Rich editor, review queue, diff/preview, validation messages, migration controls |
| Content ownership | Product/curriculum owner | Source materials, subject/topic mapping, QA acceptance, publication approval |
| Curriculum QA | Tutor/admin/content reviewer | Review notes, approval/request-changes, publish readiness, rollback acceptance |
| Release | Product/engineering owner | Migration dry-run/apply evidence, rollout state, deferred scope tracking |

## Rich Editor Contract

Editor content should support:

- Lesson sections, objectives, worked examples, formulas, code blocks, media references, and glossary terms.
- Exercise blocks with prompt, answer key, hints, explanation, difficulty, tags, prerequisites, subject/topic, locale metadata, and estimated duration.
- Preview behavior that matches published student/parent reads without exposing draft-only metadata.
- Validation errors that are actionable for authors and stable for frontend rendering.
- Diff behavior between draft, reviewed, approved, published, and rollback candidate versions.

## Migration Contract

Migration manifests should include:

- Source name, source version, source owner, import batch ID, operator, and timestamp.
- Subject/topic mapping, public lesson IDs, version IDs, exercise IDs, locale metadata, and dependency order.
- Dry-run result with created/updated/skipped/conflicted rows and validation errors.
- Apply result with written version metadata, publish readiness, audit references, and rollback metadata.
- Rollback/undo behavior that preserves existing published content until an approved pointer switch occurs.

## Assignment And Sequencing Readiness

Assignment automation should remain controlled:

- Reviewed curriculum exercises and accepted AI drafts may become assignment candidates.
- Tutor/admin approval remains required where generated content is involved.
- Signals may include curriculum progress, mistakes, AI draft outcomes, assignment outcomes, memory snapshots, and content-quality analytics.
- Student/parent surfaces should distinguish recommendations from assigned work.
- Archived or rolled-back content must not be newly assigned.

## Rollout States

- `contract-ready`: v5.1 contract and handoff docs are complete.
- `editor-ready`: rich editor API/UX handoff is ready for implementation or shipped.
- `migration-ready`: migration dry-run/apply/rollback evidence is ready.
- `assignment-ready`: reviewed assignment automation and sequencing readiness are verified.
- `blocked`: required source content, frontend ownership, or QA approval is unavailable.
- `deferred`: contract/backend readiness is complete but frontend/content migration remains future scope.

## Implementation Handoff

Phase 177 should define or implement rich editor UI/API readiness.

Phase 178 should define or implement production content migration pipeline and validation.

Phase 179 should define assignment automation and adaptive sequencing readiness.

Phase 180 should verify v5.1, record rollout state, and update the remaining-feature queue.
