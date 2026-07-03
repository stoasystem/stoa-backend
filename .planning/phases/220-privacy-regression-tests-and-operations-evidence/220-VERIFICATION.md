---
status: passed
---

# Phase 220 Verification

Commands:

- `.venv/bin/pytest tests/test_subscription_operations.py::test_parent_account_operations_combines_billing_entitlement_usage_and_verification tests/test_subscription_operations.py::test_admin_account_operations_surfaces_attention_state tests/test_subscription_operations.py::test_admin_account_operations_returns_404_for_missing_parent -q` — passed, 3 tests.
- `.venv/bin/ruff check src/stoa/services/account_operations_service.py src/stoa/db/repositories/user_repo.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py` — passed.

Broader focused regression is recorded in Phase 221 release gate after final execution.
