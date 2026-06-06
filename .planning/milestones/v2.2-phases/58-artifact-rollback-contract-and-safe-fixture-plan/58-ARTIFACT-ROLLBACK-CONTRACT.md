# Phase 58 Artifact Rollback Contract

**Status:** Accepted for Phase 59 implementation
**Scope:** v2.2 backend-mediated report artifact rollback preview/apply workflow

## Goal

Admins can roll back a report's current artifact metadata pointers to a previously recorded artifact version without direct S3 access, raw artifact exposure, or deletion of artifact history.

## Rollback Scope

Phase 59 should support rollback from the current artifact version to the immediately previous artifact version recorded on the report summary:

| Field | Purpose |
|-------|---------|
| `artifact_version_id` | Current artifact version ID. |
| `json_s3_key` | Server-side current JSON artifact key. |
| `html_s3_key` | Server-side current HTML artifact key. |
| `previous_artifact_version_id` | Target prior artifact version ID. |
| `previous_json_s3_key` | Server-side target JSON artifact key. |
| `previous_html_s3_key` | Server-side target HTML artifact key. |

Rollback to arbitrary older versions is out of scope unless existing redacted audit rows can safely provide a target version without exposing private keys or requiring broad scans.

## Preview Lifecycle

1. Admin selects a report through existing admin report operations.
2. Backend loads report summary metadata.
3. Backend validates that the report has rollback-eligible current and previous artifact metadata.
4. Backend rejects rollback preview if target version is missing, target version equals current version, or private artifact metadata is malformed.
5. Backend returns sanitized current/target version metadata, validation result, opaque preview ID if persisted, source report `updated_at`, and required apply constraints.

Preview response must not include:

- Private S3 keys.
- Presigned URLs.
- Raw report JSON.
- Raw unreviewed HTML.
- Auth/session tokens.
- Full artifact payloads.

## Apply Lifecycle

1. Admin submits rollback target and a non-empty operator reason.
2. Backend reloads the report summary.
3. Backend rejects apply if report `updated_at`, current `artifact_version_id`, current JSON key, or current HTML key differs from the preview/source snapshot.
4. Backend validates the target version metadata still exists on the report summary or in the persisted rollback preview.
5. Backend updates report metadata to point at the target version's JSON/HTML keys.
6. Backend preserves the rolled-forward version as the new `previous_*` metadata so operators can reverse the rollback if needed.
7. Backend writes append-only audit evidence.

## Metadata Update

Successful rollback should update the report summary with:

| Field | Value |
|-------|-------|
| `artifact_version_id` | Target prior artifact version ID. |
| `artifact_version_created_at` | Rollback apply timestamp or target version timestamp if safely known. |
| `artifact_version_created_by` | Rollback operator ID. |
| `json_s3_key` | Target prior JSON key. |
| `html_s3_key` | Target prior HTML key. |
| `s3_key` | Target prior HTML key for legacy compatibility. |
| `previous_artifact_version_id` | Source current artifact version ID before rollback. |
| `previous_json_s3_key` | Source current JSON key before rollback. |
| `previous_html_s3_key` | Source current HTML key before rollback. |
| `last_operation` | `rollback_report_artifact`. |
| `last_operation_result` | `success`, `refused`, or `failed`. |
| `updated_at` | Rollback apply timestamp. |

This pointer-swap model preserves both artifact versions and creates a reversible one-step rollback/roll-forward path.

## Audit Evidence

Every preview and apply/refusal event writes to the existing report audit timeline.

Required audit metadata:

- `action`: `create_report_artifact_rollback_preview` or `apply_report_artifact_rollback`.
- `actor`.
- `reason`.
- `source`.
- `result`.
- `rollback_preview_id` if persisted.
- `source_artifact_version_id`.
- `target_artifact_version_id`.
- Sanitized `before` and `after` metadata snapshots.
- `validation_result`.
- `correlation_id`.
- `event_at`.

Audit payloads must remain metadata-only and redacted.

## Privacy Denylist

Validation and response sanitization must reject or redact:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- `presignedUrl`
- `presigned_url`
- `X-Amz-`
- `https://s3`
- raw `<html` content
- bearer/auth/session token markers

## Implementation Notes For Phase 59

- Prefer a new `report_artifact_rollback_service.py` or a clearly separated rollback section in `report_artifact_edit_service.py`.
- Reuse `report_repo.try_apply_report_artifact_edit` if its generic conditional update semantics remain sufficient; rename or wrap it if rollback semantics would be clearer.
- Do not read raw artifact payloads for rollback unless needed to validate key existence. Pointer metadata validation should be enough for the initial rollback path.
- Add admin route models and endpoints under selected report operations, parallel to artifact edit preview/apply routes.
- Add focused tests for admin-only auth, missing target metadata, no-op target rejection, stale rejection, sanitized response, rollback metadata update, audit evidence, and privacy denylist.
