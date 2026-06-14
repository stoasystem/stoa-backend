# Phase 178 Production Content Migration Pipeline And Validation

## Status

Accepted as migration-readiness handoff.

Phase 178 defines how approved curriculum source material should move into STOA-managed curriculum versions without silently altering published student/parent content.

## Pipeline Stages

| Stage | Mode | Mutates Data | Purpose |
|-------|------|--------------|---------|
| Ingest source manifest | Dry-run/apply | No by itself | Parse approved source metadata and lesson/exercise rows. |
| Normalize | Dry-run/apply | No | Convert source fields into STOA lesson bundle shape. |
| Validate | Dry-run/apply | No | Check required fields, IDs, dependencies, answer keys, locale, and publish readiness. |
| Diff/conflict detect | Dry-run/apply | No | Compare source rows against existing public IDs, versions, and published pointers. |
| Apply versions | Apply only | Yes | Create draft/version rows and migration evidence under approval. |
| Publish sequencing | Optional later step | Yes | Publish approved versions through existing compare-and-set manifest behavior. |
| Rollback/undo | Operator action | Yes, pointer-safe | Restore prior published pointer or archive bad imported versions without hard deletion. |

## Source Manifest Schema

Required batch metadata:

- `batchId`
- `sourceName`
- `sourceVersion`
- `sourceOwner`
- `approvedBy`
- `operatorId`
- `createdAt`
- `defaultLocale`
- `supportedLocales`
- `publishMode`: `draft_only`, `approved_only`, or `publish_after_approval`

Required lesson row fields:

- source lesson ID
- STOA public lesson ID
- title
- objective
- subject ID
- topic ID
- unit ID
- grade level
- difficulty
- locale
- estimated minutes
- dependency/prerequisite lesson IDs

Required exercise row fields:

- source exercise ID
- STOA public exercise ID
- parent public lesson ID
- prompt
- type
- order
- difficulty
- answer key
- hints
- explanation
- skills/tags
- estimated minutes

## Mapping Rules

- Public IDs must be deterministic and URL-safe.
- Existing public IDs may be updated only when the operator declares the intended update mode.
- Source IDs are recorded for traceability but never become the primary public API identity.
- Subject/topic/unit references must match existing catalog values or be declared as new content rows in the same batch.
- Locale metadata is required even for default-language source content.
- Dependency ordering must ensure prerequisite lessons exist before dependent lessons are publish-ready.

## Dry-Run Contract

Dry-run returns:

| Field | Meaning |
|-------|---------|
| `batchId` | Source batch identity. |
| `mode` | Always `dry_run`. |
| `created` | Rows that would create new public IDs. |
| `updated` | Rows that would create new versions for existing public IDs. |
| `skipped` | Rows identical to existing current content or excluded by manifest rules. |
| `conflicted` | Rows with public ID collision, stale source version, dependency mismatch, or incompatible update intent. |
| `validationErrors` | Field-level errors grouped by lesson/exercise row. |
| `publishReadiness` | Whether each lesson bundle can enter review/publish after apply. |
| `rollbackPlan` | Previous pointer/version metadata needed if apply/publish later fails. |

Dry-run must not write versions, pointers, manifests, published projections, audit events, or analytics signals.

## Apply Contract

Apply requires:

- exact `batchId`
- approved dry-run result hash or revision ID
- operator ID
- approval reason
- explicit target set or full-batch selection
- expected current published version IDs for any update that may later publish

Apply writes:

- version rows for lesson bundles
- migration evidence row with source metadata, result counts, dry-run hash, operator, timestamp, and approval reason
- audit events for created/updated/skipped/conflicted rows as appropriate
- rollback metadata linking each created version to prior published pointer state

Apply does not automatically publish unless the approved mode and release gate permit it. Default v5.1 posture is apply-to-draft/readiness, not production publication.

## Conflict And Validation Rules

Block by default when:

- Required lesson or exercise fields are missing.
- Answer keys or explanations are missing for publish-ready exercises.
- Public IDs collide with unrelated subject/topic content.
- Source update attempts to replace a current published version without an expected pointer.
- Prerequisite/dependency lessons are missing or ordered after dependents.
- Locale metadata is absent.
- Existing active assignments reference content that would be archived or repointed unsafely.

Allow with warning when:

- Source row is identical to current content.
- Optional rich fields are unsupported by current backend payloads but preserved in migration metadata.
- A lesson is draft-ready but not publish-ready because exercises are incomplete.

## Rollback And Undo

Rollback is pointer-safe:

- Version rows are immutable and remain in history.
- Published pointer rollback uses the existing `rollback` service path and compare-and-set expectations.
- Draft-only bad imports can be archived with audit evidence.
- Applied migration evidence records previous published pointers, created version IDs, and undo eligibility.

No migration cleanup should hard-delete version history or audit evidence.

## Operator And Frontend Handoff

Future admin UI should provide:

- manifest upload or source selection
- dry-run results table
- validation/conflict filters
- apply subset selector
- approval reason input
- evidence download/copy
- rollback eligibility view

Backend implementation should add a dedicated migration service rather than overloading `curriculum_ops_service` with source parsing.

## Test Targets

- Dry-run returns created/updated/skipped/conflicted rows without repository writes.
- Validation failures include field-level lesson/exercise paths.
- Apply refuses without approved dry-run hash and operator reason.
- Apply writes migration evidence and version metadata.
- Conflict detection catches public ID collision and stale pointer conditions.
- Rollback metadata can restore previous published pointer through existing rollback behavior.

## Acceptance Mapping

| CURRICULUMXP-03 Criterion | Status |
|---------------------------|--------|
| Manifest supports source, subject/topic mapping, public/version IDs, locale metadata, exercises, and dependencies. | Satisfied by manifest and mapping contract. |
| Dry-run reports created/updated/skipped/conflicted rows and validation errors without mutation. | Satisfied by dry-run contract. |
| Apply mode writes migration evidence, version metadata, and audit under explicit approval. | Satisfied by apply contract. |
| Rollback/undo metadata protects existing published content. | Satisfied by rollback contract. |
| Tests/checks cover dry-run, conflict detection, validation failures, apply evidence, and rollback metadata. | Test targets defined; implementation deferred. |

## Release Classification

Phase 178 is `migration-ready` as a pipeline contract. It is not a production content import.
