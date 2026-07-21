# Deferred Items

## 475-01

- Targeted mypy over the two changed runtime modules still reports five pre-existing
  `object`-to-`int` narrowing errors in unchanged reconciliation code at
  `src/stoa/services/usage_ledger_service.py:549`, `:550`, `:559`, `:608`, and
  `:619`. The new `question_submission_repo.py` passes mypy independently. These
  existing reconciliation typing errors are outside Plan 475-01's atomic admission
  boundary and were not modified.
