---
status: passed
---

# Phase 217 Verification

`account_operations_service` now defines the shared aggregation contract and support-state logic. It reuses existing data sources and introduces no new infrastructure.

Commands:

- `.venv/bin/pytest tests/test_subscription_operations.py::test_parent_account_operations_combines_billing_entitlement_usage_and_verification tests/test_subscription_operations.py::test_admin_account_operations_surfaces_attention_state tests/test_subscription_operations.py::test_admin_account_operations_returns_404_for_missing_parent -q` — passed.
- `.venv/bin/ruff check src/stoa/services/account_operations_service.py src/stoa/db/repositories/user_repo.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py` — passed.
