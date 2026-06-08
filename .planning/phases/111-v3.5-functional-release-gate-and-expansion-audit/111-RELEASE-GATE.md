# v3.5 Release Gate

**Milestone:** v3.5 Realtime And Teacher Assistance Foundation
**Status:** Passed for local release gate
**Date:** 2026-06-08

## Commit Evidence

Backend commits:

- `b9d6af6` - `docs: plan v3.5 notification assistance milestone`
- `f70b4ac` - `docs(108): complete notification assistance contract`
- `0d8e278` - `feat(109): add notification events and assistance seeds`
- `4a74126` - `docs(110): complete notification assistance UI phase`

Frontend commit:

- `ea90f71` - `feat(110): add notification and assistance UI`

## Backend Verification

| Check | Result | Notes |
|-------|--------|-------|
| `./.venv/bin/python -m pytest` | Passed | `297 passed in 5.39s` |
| Focused Ruff on v3.5 changed backend/test files | Passed | Notification repo/service/router, teacher assistance service, touched routers/services, and `tests/test_notifications.py` lint cleanly |
| `./.venv/bin/ruff check .` | Failed on known legacy lint | 34 existing issues in practice/conversations/deps/seed code outside the v3.5 notification and assistance changes |

## Frontend Verification

| Check | Result | Notes |
|-------|--------|-------|
| `npm run lint` | Passed | v3.5 frontend notification and assistance UI lint clean |
| `npm run build` | Passed | Existing Vite chunk-size warning only |
| `npx playwright test tests/e2e/tutor-workflow.spec.ts` | Passed | `2 passed`; covered tutor assistance summary and admin operational notifications |

## Release Decision

v3.5 passes the local functional release gate. The milestone is ready to close as a foundation release, with production deployment and live WebSocket/push delivery intentionally out of scope.

## Residual Gate Notes

- Broad backend Ruff remains blocked by unrelated legacy lint in `scripts/seed_practice.py`, `src/stoa/db/repositories/practice_repo.py`, `src/stoa/deps.py`, `src/stoa/routers/conversations.py`, `src/stoa/routers/files.py`, and `src/stoa/routers/practice.py`.
- No production deployment or live smoke was performed for v3.5.
- Full realtime transport, push/email notification delivery, and automatic exercise generation remain future milestones.
