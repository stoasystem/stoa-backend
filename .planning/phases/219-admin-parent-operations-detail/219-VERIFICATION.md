---
status: passed
---

# Phase 219 Verification

Admin account operations detail is available at `GET /admin/account-operations/parents/{parent_id}`.

Commands:

- `.venv/bin/pytest tests/test_subscription_operations.py::test_admin_account_operations_surfaces_attention_state tests/test_subscription_operations.py::test_admin_account_operations_returns_404_for_missing_parent -q` — passed.
