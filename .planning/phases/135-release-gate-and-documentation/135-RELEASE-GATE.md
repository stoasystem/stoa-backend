# v4.1 Release Gate

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Phase:** 135
**Date:** 2026-06-11
**Status:** Passed for local backend completion

## Verification Results

| Gate | Result | Evidence |
|------|--------|----------|
| Full backend tests | Passed | `.venv/bin/python -m pytest` -> 325 passed. |
| Changed-file ruff slices | Passed | Phase 133 and 134 focused ruff checks passed on changed files. |
| Full ruff | Known pre-existing failures | `.venv/bin/python -m ruff check src tests` reports 13 unrelated issues in `src/stoa/deps.py`, `src/stoa/routers/conversations.py`, and `src/stoa/routers/files.py`. |
| Planning traceability | Passed | Requirements and roadmap updated for v4.1 completion. |
| Deferred scope recorded | Passed | Frontend/native responsive UI, visual localization, and production smoke remain explicitly deferred. |

## Full Ruff Failure Details

Current full ruff failures are unrelated to v4.1 changes:

- `src/stoa/deps.py`: unused `json`, unused `base64url_decode`.
- `src/stoa/routers/conversations.py`: unused imports, module-level import order, and one multiple-import line.
- `src/stoa/routers/files.py`: unused `re`.

These existed as known repository hygiene debt before v4.1 and are not introduced by the locale/mobile contract work.

## Local Completion Scope

Completed:

- Backend mobile/multilingual contract.
- Durable locale preference API foundation.
- Locale metadata on selected adaptive student/parent/tutor/admin routes.
- Canonical-value stability tests across `de` and `en`.
- Feature gap audit and milestone documentation updates.

Not completed:

- Production deployment or live smoke.
- Responsive frontend/mobile viewport verification.
- Native mobile app work.
- Translated UI copy and visual localization.
- RTL visual verification.
- Machine translation or translation management.
