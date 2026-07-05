# Phase 250 Verification

status: passed

## Backend Tests

```bash
.venv/bin/pytest tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py tests/test_curriculum_analytics.py tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger
```

Result:

- `43 passed in 1.34s`

## Backend Lint

```bash
.venv/bin/ruff check src/stoa/services/core_smoke_service.py src/stoa/routers/admin.py tests/test_core_smoke.py
```

Result:

- `All checks passed!`

## Residual Risk

- This is a deterministic local smoke matrix, not a live provider smoke.
- Live Cognito/email, Stripe/TWINT, notification, AI provider, and external support-provider checks remain externally blocked unless separately approved.
