# Phase 58: Artifact Rollback Contract And Safe Fixture Plan - Context

**Gathered:** 2026-06-06
**Status:** Ready for implementation planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 58 defines rollback and production safe-fixture verification before any rollback mutation code. It consumes v2.1 artifact edit behavior, preserves the backend-mediated artifact privacy boundary, and decides whether existing CDK resources can support rollback.

</domain>

<decisions>
## Implementation Decisions

### Rollback Model
- Rollback is a backend-mediated current-pointer switch from the current artifact version to a previously recorded artifact version.
- Rollback does not delete prior JSON/HTML artifacts.
- Rollback must validate the current report `updated_at`, current `artifact_version_id`, and current JSON/HTML artifact keys before metadata update.
- Rollback must expose only opaque version IDs, timestamps, validation state, and audit references to the frontend.

### Target Version Scope
- v2.2 starts with the previous version recorded by v2.1 metadata: `previous_artifact_version_id`, `previous_json_s3_key`, and `previous_html_s3_key`.
- A broader multi-version history browser remains future scope unless Phase 59 finds existing audit rows can safely provide sanitized version choices without extra storage work.

### Safe Fixture Scope
- Production mutation smoke remains opt-in and fixture-only.
- The harness must refuse to mutate unless an explicit fixture name and explicit mutation mode are supplied.
- Smoke evidence must record request IDs, sanitized version metadata, rollback metadata, cleanup/restore result, and privacy denylist results.

### the agent's Discretion
- Phase 59 may implement rollback preview as an ephemeral validation response or a persisted preview row. Persisted preview is preferred if it reduces stale-apply risk and matches v2.1 preview/apply ergonomics.

</decisions>

<code_context>
## Existing Code Insights

- `report_artifact_edit_service.py` writes versioned artifacts and records previous artifact version/key metadata on successful apply.
- `report_repo.try_apply_report_artifact_edit` already supports conditional report summary updates against `updated_at`, `artifact_version_id`, `json_s3_key`, and `html_s3_key`.
- Admin route responses already include sanitized artifact metadata and an `edit_artifact` action state.
- Phase 55 tests include privacy marker denylist coverage for artifact edit preview/apply responses and audit events.

</code_context>

<deferred>
## Deferred Ideas

- Arbitrary version history browser.
- Rollback of non-immediate prior versions unless existing redacted audit metadata can support it safely.
- WORM audit storage.
- Freeform WYSIWYG editing.

</deferred>
