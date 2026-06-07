---
phase: 67-backend-support-handoff-package-apis
reviewed: 2026-06-07T08:01:14Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/stoa/services/support_handoff_service.py
  - src/stoa/routers/admin.py
  - src/stoa/db/repositories/report_repo.py
  - tests/test_admin_report_ops.py
findings:
  critical: 3
  warning: 1
  info: 0
  total: 4
status: fixed
---

# Phase 67: Code Review Report

**Reviewed:** 2026-06-07T08:01:14Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

**Fix Status:** fixed after review

## Summary

Reviewed the Phase 67 support handoff service, admin route, audit repository addition, and focused admin tests against HANDOFF-03/HANDOFF-04. The route is admin-only and `external_write` skips recovery/fixture evidence reads, but the package privacy boundary has blocking gaps: credential-like free text can be returned and audited, failed release-evidence privacy validation is not propagated to the package result, and release evidence can be echoed as a sanitized-but-not-allowlisted bundle.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Free-text credential markers pass through package and audit output

**File:** `src/stoa/services/support_handoff_service.py:49`
**Issue:** `reason`, `generated_by`, `operator_note`, and audit `reason`/`actor` are redacted only through `report_recovery_service.redact_private_artifact_text`. That helper covers report artifact URLs/keys but not the v2.4 denylist markers asserted by the tests (`access_token`, `id_token`, `refresh_token`) or adjacent credential text such as `password`, `secret`, and `cookie`. Because `private_marker_hits(package)` is run after these strings are added and its text patterns do not include those credential names, a request like `{"reason": "access_token=SECRET", "operator_note": "refresh_token=SECRET"}` returns those values with `validation.privacy.passed = true` and also stores the raw reason in the support handoff audit event at lines 167-184.
**Fix:**
```python
# Centralize this in the release evidence/privacy helper if possible.
PRIVATE_FREE_TEXT_PATTERN = re.compile(
    r"\b(access_token|id_token|refresh_token|password|secret|cookie)\b\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)

def _redact_text(value: object) -> str | None:
    text = report_recovery_service.redact_private_artifact_text(value)
    if text is None:
        return None
    return PRIVATE_FREE_TEXT_PATTERN.sub("[private-credential]", text)
```
Then add a package-level violation/refusal test for token/password text in `reason`, `operator_note`, and audit metadata.

### CR-02: Failed release-evidence validation still produces an overall ready/passed package

**File:** `src/stoa/services/support_handoff_service.py:73`
**Issue:** `_release_validation_result()` can return `status: "failed"` and `privacy.passed: false`, but `build_package()` places that result in a section and leaves the top-level `validation.status` as `"passed"` unless the final `private_marker_hits(package)` catches something. It does not catch private-key violations such as `json_s3_key` once the validated section records them as `{"marker": "json_s3_key"}`. The observed result is a `release_evidence_validation` section with failed privacy, while `destination.status` remains `"ready"`, `validation.status` remains `"passed"`, and the audit row records `result: generated`.
**Fix:**
```python
validation_failures: list[str] = []

if release_evidence is not None:
    validated = _release_validation_result(release_evidence)
    if validated.get("status") != "passed" or not validated.get("privacy", {}).get("passed", True):
        validation_failures.append("release evidence validation failed")
    sections.append({...})

validation_status = "refused" if refusal_reasons else "failed" if validation_failures else "passed"
package["validation"]["status"] = validation_status
if validation_failures:
    package["destination"]["status"] = "refused"
    package["destination"]["refusal_reasons"].extend(validation_failures)
```
Also assert the audit metadata records the refused/failed result when release evidence validation fails.

### CR-03: Release evidence output is sanitized by denylist, not constrained to metadata-only fields

**File:** `src/stoa/services/support_handoff_service.py:81`
**Issue:** The handoff package embeds the full `validated` release-evidence result, which includes the sanitized submitted `bundle`. Sanitization removes known private keys and some text patterns, but it does not enforce an allowlist or reject unknown content. An admin mistake can include arbitrary raw operational/customer data under keys that are not currently denylisted, and the support package will echo it while still claiming `metadata_only: true`. This violates the HANDOFF-03 metadata-only boundary and makes privacy depend on a partial denylist.
**Fix:**
```python
def _release_validation_summary(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": validated.get("schema_version"),
        "validated_at": validated.get("validated_at"),
        "status": validated.get("status"),
        "missing_required_fields": validated.get("missing_required_fields", []),
        "schema_errors": validated.get("schema_errors", []),
        "status_errors": validated.get("status_errors", []),
        "fixture_errors": validated.get("fixture_errors", []),
        "privacy": validated.get("privacy", {}),
    }
```
Use that summary in the handoff section instead of returning `validated["bundle"]`, or explicitly allowlist each release bundle field that is safe to hand off.

## Warnings

### WR-01: Focused tests miss the privacy-denial and validation-failure branches

**File:** `tests/test_admin_report_ops.py:2113`
**Issue:** The support handoff tests cover a happy path with report artifact redaction, missing references, `external_write`, and unknown destination rejection, but they never submit credential denylist text or a release-evidence bundle whose validation fails. The assertions at lines 2180-2181 only prove the passing path. This allowed CR-01 and CR-02 to ship despite `_assert_no_private_artifact_markers` listing token markers.
**Fix:** Add tests that POST `/admin/reports/support-handoff-package` with `reason`/`operator_note` containing `access_token`, `id_token`, and `refresh_token`, and with `release_evidence` containing a private key such as `json_s3_key`. Assert the response and persisted support audit row contain no marker text and that the package/audit result is refused or failed.

---

_Reviewed: 2026-06-07T08:01:14Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_

## Fix Verification

All findings were addressed after review:

- CR-01 fixed by adding support-handoff free-text credential redaction for access/id/refresh tokens, passwords, secrets, and cookies before package and audit output.
- CR-02 fixed by propagating failed release evidence validation and missing recovery references to top-level package refusal and refused audit result.
- CR-03 fixed by replacing echoed release validation bundles with an allowlisted validation summary.
- WR-01 fixed by adding regression tests for credential free text and failed release evidence validation.

Verification rerun under `.venv`:

- `python -m pytest tests/test_admin_report_ops.py -k "support_handoff or recovery_job_support_package or recovery_evidence"`: 14 passed, 54 deselected.
- `python -m ruff check src/stoa/services/support_handoff_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py`: passed.
