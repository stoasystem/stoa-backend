# Phase 89 Summary

Phase 89 implemented account lifecycle and parent binding hardening.

Completed:

- Added `POST /auth/forgot-password`.
- Added `POST /auth/reset-password`.
- Added explicit `emailVerificationStatus` in auth responses and profile metadata for the current admin-marked-verified registration decision.
- Added formal parent-student binding rows in `user_repo`.
- Updated parent portal ownership reads to prefer formal bindings and fall back to legacy student profile links.
- Updated weekly report pair discovery to include formal bindings and de-duplicate legacy links.
- Added admin-only `/admin/parent-bindings` inspection and `/admin/parent-bindings/repair` repair endpoints.
- Added tests for reset flow, token non-leakage, pending one-sided binding claims, mutual binding activation, admin repair, parent portal binding reads, and weekly discovery.

Verification:

- `PYTHONPATH=src .venv/bin/python -m pytest -q` -> 257 passed.
- `.venv/bin/ruff check ...` -> all checks passed.

