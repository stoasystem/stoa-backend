---
phase: 101-backend-subscription-request-and-admin-tier-apis
reviewed: 2026-06-08T12:50:21Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/parents.py
  - src/stoa/routers/admin.py
  - tests/test_subscription_operations.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
resolved_findings:
  critical: 3
  warning: 1
---

# Phase 101: Code Review Report

**Reviewed:** 2026-06-08T12:50:21Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** clean after fixes

## Summary

Reviewed the scoped subscription service, parent/admin route additions, and subscription operation tests. The initial review found three blockers and one warning. Those findings were fixed by adding a parent open-request guard, transaction-backed create/update/apply paths, paginated request scans, key-aware event history tests, and pagination/guard tests.

Verification after fixes:

- `./.venv/bin/python -m pytest` - 286 passed.
- `./.venv/bin/python -m ruff check src/stoa/services/subscription_service.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py` - passed.
- `./.venv/bin/python -m ruff check .` - blocked by pre-existing unrelated lint outside this phase's write set.

## Resolution Summary

- CR-01 fixed: `create_parent_request` now creates summary, event, and `SUBSCRIPTION_OPEN#<parent_id>` guard in one transaction with conditional puts.
- CR-02 fixed: `_list_requests` now follows `LastEvaluatedKey` until the scan is exhausted before applying response limits.
- CR-03 fixed: `apply_request` now updates the user profile, request summary, event row, and open guard in one transaction with an approved-status condition.
- WR-01 fixed: tests now cover paginated scans, guard-backed pending request lookup, and request-specific event history isolation.

## Critical Issues

### CR-01: BLOCKER - Duplicate Open Requests Are Not Prevented Atomically

**File:** `src/stoa/services/subscription_service.py:89`

**Status:** Resolved.

**Issue:** `create_parent_request` checked `_latest_open_request(parent_id)` before writing, then performed unconditional `put_item` calls. Two concurrent submissions could both observe no open request and create separate open requests for the same parent.

**Fix:** Added a per-parent open-request guard item and transaction-backed create/terminal cleanup.

### CR-02: BLOCKER - Request Listing Reads Only One DynamoDB Scan Page

**File:** `src/stoa/services/subscription_service.py:283`

**Status:** Resolved.

**Issue:** `_list_requests` performed a single `scan` and never followed `LastEvaluatedKey`.

**Fix:** `_list_requests` now loops through scan pages until exhaustion.

### CR-03: BLOCKER - Applying A Request Can Partially Mutate Parent Tier

**File:** `src/stoa/services/subscription_service.py:223`

**Status:** Resolved.

**Issue:** `apply_request` updated the parent profile tier before updating the request status and writing the audit event.

**Fix:** `apply_request` now uses one transaction for user profile update, request update, event insert, and open-guard delete with a request status condition.

## Warnings

### WR-01: WARNING - Tests Do Not Exercise DynamoDB Pagination Or Key Filtering

**File:** `tests/test_subscription_operations.py:21`

**Status:** Resolved.

**Issue:** The original fake table did not exercise pagination or key-specific event history.

**Fix:** Added paginated scan behavior, key-aware event queries, and tests for pagination, guard-backed pending request lookup, and event history isolation.

---

_Reviewed: 2026-06-08T12:50:21Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
