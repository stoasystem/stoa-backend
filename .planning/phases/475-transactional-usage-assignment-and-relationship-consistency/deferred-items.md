# Deferred Items

## 475-01

- Targeted mypy over the two changed runtime modules still reports five pre-existing
  `object`-to-`int` narrowing errors in unchanged reconciliation code at
  `src/stoa/services/usage_ledger_service.py:549`, `:550`, `:559`, `:608`, and
  `:619`. The new `question_submission_repo.py` passes mypy independently. These
  existing reconciliation typing errors are outside Plan 475-01's atomic admission
  boundary and were not modified.

## 475-06

- Targeted mypy over the changed runtime modules retains pre-existing provider-boundary
  typing debt: seven `get_table()` capability errors in unchanged `user_repo.py` reads,
  one unrelated locale response narrowing error in `auth.py`, and 43 unrelated admin
  projection/table capability errors in `admin.py`. The new parent relationship code
  adds no mypy errors; these existing errors are outside the atomic binding boundary.
