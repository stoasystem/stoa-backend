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

## 475-10

- Targeted mypy over `practice_repo.py` retains 16 pre-existing DynamoDB table
  capability errors in unchanged repository reads/writes. The changed practice model
  and projection service pass mypy independently.
- The optional expanded learning regression retains one stale question-submission
  fixture (`test_submit_question_accepts_foundation_subject_and_stores_topic_seeds`)
  that mocks the pre-475-02 non-atomic route and now receives the expected safe 503.
  The other 68 practice authorization, privacy-deletion, curriculum analytics, and
  learning-expansion nodes passed; the stale question fixture is outside Plan 475-10.

## 475-28

- Expanded Ruff over the inherited notification-deletion regression reports a
  pre-existing unused `account_deletion_repo` import in
  `tests/test_phase473_notification_deletion.py:10`. The inherited behavior suite
  passes all nodes, and the planned repository and proof files pass Ruff; this
  unchanged lint issue is outside Plan 475-28 and was not modified.
