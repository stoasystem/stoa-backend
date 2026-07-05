# Phase 248 Context

## Milestone

v5.15 Usage, Quota, And Product Stability

## Requirement

LEDGER-01 Ledger Coverage And Idempotency Closure

## Inputs From Phase 247

Phase 247 found that the existing ledger taxonomy covered most high-value student learning flows, but four stability gaps needed immediate closure:

- Practice teacher-help had a backend/frontend path but no support-visible usage event.
- Question submit accepted the same idempotency key for a different submitted question intent.
- Partial failure between question counter/ledger writes and question persistence needed focused test evidence.
- Runtime changes had to preserve the existing content/privacy boundary.

## Files Changed

- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/routers/practice.py`
- `src/stoa/routers/questions.py`
- `tests/test_usage_ledger.py`
- `tests/test_curriculum_analytics.py`
- `tests/test_questions.py`

## Constraints

- Do not add raw learning content, prompts, answers, teacher-help message bodies, provider payloads, tokens, verification codes, or private artifact keys to usage ledger events.
- Keep existing successful route response shapes compatible.
- Treat broad quota reconciliation status changes as Phase 249 work.
