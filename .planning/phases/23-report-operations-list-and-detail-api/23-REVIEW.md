---
phase: 23-report-operations-list-and-detail-api
reviewed: 2026-06-04T15:14:02Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/stoa/db/repositories/report_repo.py
  - src/stoa/routers/admin.py
  - tests/test_admin_report_ops.py
  - tests/test_parent_children.py
  - .planning/phases/23-report-operations-list-and-detail-api/23-CONTEXT.md
  - .planning/phases/23-report-operations-list-and-detail-api/23-01-PLAN.md
  - .planning/phases/23-report-operations-list-and-detail-api/23-01-SUMMARY.md
  - .planning/phases/23-report-operations-list-and-detail-api/23-VERIFICATION.md
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: fixed
---

# Phase 23: Code Review Report

**Reviewed:** 2026-06-04T15:14:02Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** fixed

## Summary

Reviewed the focused Phase 23 source, tests, and phase artifacts for admin report operations list/detail behavior, privacy boundaries, pagination, and test coverage. The implementation currently violates the stated privacy requirement by returning private report artifact S3 keys, and malformed-but-decodable pagination tokens can reach DynamoDB as unvalidated `ExclusiveStartKey` values. The test and verification artifacts also miss the direct S3 path case and currently encode the privacy leak as expected behavior.

## Resolution

All findings were fixed before the Phase 23 commit:

- `artifact_keys` was replaced with non-addressable `artifacts` availability booleans.
- Privacy tests now reject `artifact_keys`, `s3_key`, `html_s3_key`, `json_s3_key`, and `weekly-reports/` in serialized admin responses.
- Pagination tokens now must decode to a report summary key before use.
- Focused tests reran after fixes: `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 73 passed.
- Ruff reran after fixes and passed.

## Critical Issues

### CR-01: [BLOCKER] Admin ops response exposes private S3 artifact paths

**File:** `src/stoa/routers/admin.py:317`

**Issue:** `_report_operation_response` returns `artifact_keys` containing `json_s3_key` and `html_s3_key` values at lines 317-320. Those values are canonical private S3 object paths such as `weekly-reports/{parent_id}/{student_id}/{week_start}/report.html`. Phase context explicitly says report ops responses must not return raw report HTML/JSON, public URLs, presigned URLs, or direct S3 fetch paths, and the user restated the same privacy requirement. This response leaks the report artifact storage path to the frontend/API caller.

**Fix:** Remove artifact keys from `ReportOperationResponse`, or replace them with non-addressable metadata such as booleans:

```python
artifacts={
    "json_available": bool(report.get("json_s3_key")),
    "html_available": bool(report.get("html_s3_key") or report.get("s3_key")),
}
```

Update tests to assert `artifact_keys`, `json_s3_key`, `html_s3_key`, `s3_key`, and `weekly-reports/` are absent from serialized admin ops responses.

### CR-02: [BLOCKER] Decodable invalid pagination tokens can produce unhandled DynamoDB errors

**File:** `src/stoa/db/repositories/report_repo.py:75`

**Issue:** `decode_page_token` accepts any JSON object as a valid token and returns it directly as an `ExclusiveStartKey`. A caller can send a base64-url token for `{"foo":"bar"}`; it passes lines 79-86, then `list_report_operations` forwards it to `list_reports_for_admin` at `src/stoa/routers/admin.py:198`, and the repository passes it to `table.query` or `table.scan` at `src/stoa/db/repositories/report_repo.py:145` and `src/stoa/db/repositories/report_repo.py:171`. DynamoDB requires `ExclusiveStartKey` to match the table/index key schema, so this can become an unhandled `ValidationException`/500 instead of the intended 400 invalid token response.

**Fix:** Validate decoded tokens before returning them, and catch repository-level validation failures in the route. At minimum require the expected key fields and scalar string values used by this table/index, then raise `ValueError` for anything else:

```python
if not isinstance(decoded, dict):
    raise ValueError("Invalid pagination token")
if not isinstance(decoded.get("PK"), str) or not isinstance(decoded.get("SK"), str):
    raise ValueError("Invalid pagination token")
```

Add route/repository tests using a base64-encoded JSON object with missing or wrong key fields and assert the API returns 400 without calling DynamoDB.

## Warnings

### WR-01: [WARNING] Privacy tests and verification omit direct S3 path assertions

**File:** `tests/test_admin_report_ops.py:70`

**Issue:** The detail test asserts `artifact_keys` equals private S3 paths at lines 70-73, and the list test only checks for `<html`, `publicUrl`, `presignedUrl`, and `https://s3` at lines 156-160. The phase verification repeats the same incomplete privacy evidence in `.planning/phases/23-report-operations-list-and-detail-api/23-VERIFICATION.md:39`. This misses the explicit direct S3 fetch path requirement and lets the CR-01 leak pass as expected behavior.

**Fix:** Change the tests to reject storage-addressable fields and path prefixes:

```python
serialized = str(data)
for forbidden in ("artifact_keys", "s3_key", "html_s3_key", "json_s3_key", "weekly-reports/"):
    assert forbidden not in serialized
```

Update the verification artifact after the corrected tests pass so it records direct S3 path coverage, not only URL coverage.

---

_Reviewed: 2026-06-04T15:14:02Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
