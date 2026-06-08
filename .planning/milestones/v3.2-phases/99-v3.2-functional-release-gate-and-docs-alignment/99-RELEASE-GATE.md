# v3.2 Release Gate

**Milestone:** v3.2 Content Moderation And Internal Operations
**Status:** Passed
**Date:** 2026-06-08

## Code SHAs

- Backend code: `61b1900` (`feat: add moderation reporting APIs`)
- Backend planning closeout at release push: `0fc3b5a` (`docs(98): complete moderation UI phase`)
- Frontend: `a148679` (`feat: add moderation operations UI`)

## Local Quality Gates

| Gate | Result |
|------|--------|
| Backend full pytest | Passed: `278 passed` |
| Backend focused ruff | Passed |
| Frontend lint | Passed |
| Frontend build | Passed |
| Frontend moderation e2e | Passed: `tests/e2e/moderation-workflow.spec.ts` (`2 passed`) |
| Frontend tutor workflow regression | Passed: `tests/e2e/tutor-workflow.spec.ts` (`2 passed`) |

## Deploy Evidence

| Repo | Workflow | Run | SHA | Result |
|------|----------|-----|-----|--------|
| `stoa-backend` | Deploy Backend | `27135978129` | `0fc3b5a` | Success |
| `stoa-frontend` | Frontend CI | `27135977993` | `a148679` | Success |
| `stoa-frontend` | Deploy Frontend | `27135978021` | `a148679` | Success |

## Production-Safe Smoke

| Check | Result |
|-------|--------|
| `GET https://api.stoaedu.ch/health` | `200`, body `{"status":"ok","version":"0.1.0"}`, request id `epAx2hgh5icEKhw=` |
| `GET https://api.stoaedu.ch/admin/moderation/cases` without auth | `401`, request id `epAx2h_EZicEJaw=` |
| `HEAD https://app.stoaedu.ch/admin/moderation` | `200`, `Last-Modified: Mon, 08 Jun 2026 11:58:15 GMT` |
| `HEAD https://app.stoaedu.ch/` | `200`, `Last-Modified: Mon, 08 Jun 2026 11:58:15 GMT` |

## Safety Notes

- No production moderation case, report artifact, teacher reply, account, legal hold, or support handoff mutation was performed during smoke.
- Backend moderation responses expose previews and omit private image/S3 keys.
- Frontend demo browser smoke through Node REPL was attempted, but Chromium launch was blocked by sandbox Mach port permissions; targeted Playwright browser tests passed with approved filesystem access.

## Residual Gaps

- Production mutation verification of moderation case creation requires a named non-customer safe fixture and cleanup path.
- Phase 2 items remain out of scope: Stripe/TWINT, broad multi-subject rollout, student memory, AI teacher assistance tools, WebSocket notifications, mobile/multilingual polish, and direct support-ticket integrations.
