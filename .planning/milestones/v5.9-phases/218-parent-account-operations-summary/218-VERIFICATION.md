---
status: passed
---

# Phase 218 Verification

`GET /parents/me/account-operations` returns parent, billing, child entitlement, usage, verification, and support state through existing parent ownership resolution.

Command:

- `.venv/bin/pytest tests/test_subscription_operations.py::test_parent_account_operations_combines_billing_entitlement_usage_and_verification -q` — passed.
