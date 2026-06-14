# Phase 178 Context: Production Content Migration Pipeline And Validation

## Why This Phase Exists

STOA has curriculum catalog, authoring, publish/rollback/archive, and analytics foundations, but production curriculum content still needs a repeatable import path from approved source material into STOA-managed lesson and exercise versions.

Phase 178 defines the migration pipeline and validation contract so future implementation can safely dry-run, apply, audit, and roll back content batches.

## Phase Boundary

This phase defines migration readiness. It does not import real production source content, publish migrated content, or replace existing published curriculum projections.

## Implementation Decisions

### Migration Mode

- Use a manifest-driven import model.
- Dry-run is the default and must be non-mutating.
- Apply mode requires explicit operator approval and writes version/audit/migration evidence.
- Publish remains a separate approval step unless a future migration mode explicitly includes approved publish sequencing.

### Content Identity

- Source IDs map to STOA stable public IDs.
- Version IDs remain immutable and are created per applied lesson bundle.
- Existing published pointers are not overwritten without compare-and-set expectations.
- Locale metadata must be present even when only English/German content is active.

### Validation

- Validate subject/topic/unit mapping, public ID collisions, required lesson fields, exercise answer keys/explanations, ordering, prerequisites, dependencies, and publish readiness.
- Report created/updated/skipped/conflicted rows in dry-run.
- Treat validation failures and conflicts as batch blockers unless the operator explicitly scopes an apply subset.

### Rollback

- Preserve previous published pointers and manifest IDs.
- Record migration batch ID, source version, actor, timestamp, and rollback metadata.
- Undo should be pointer-safe: rollback to a previous approved/published version, not hard-delete version history.

## Existing Code Insights

- `curriculum_ops_service.publish` and `rollback` already use publish manifests and expected published-version checks.
- `curriculum_ops_service.create_lesson_draft` already normalizes lesson and exercise payloads into version rows.
- `curriculum_ops_repo` owns version, pointer, manifest, and audit storage.
- `tests/test_curriculum_ops.py` already covers publish, rollback, stale pointer, archive refusal, and draft isolation.

## Deferred Ideas

- Actual migration CLI/API implementation.
- Real source document parsing.
- Operator upload UI.
- Automatic publish after migration.
- Production content approval workflow outside the repository.
