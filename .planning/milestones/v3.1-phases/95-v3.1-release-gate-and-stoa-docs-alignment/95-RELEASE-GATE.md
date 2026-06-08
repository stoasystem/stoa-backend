# v3.1 Release Gate

**Milestone:** v3.1 Teacher Reply Quality And SLA Operations
**Status:** Passed
**Date:** 2026-06-08

## Code SHAs

- Backend: `70cb8ae` (`feat: expose tutor reply sla metadata`)
- Frontend: `b6c0fc4` (`feat: add teacher reply composer sla UI`)

## Local Quality Gates

| Gate | Result |
|------|--------|
| Backend full pytest | Passed: `271 passed` |
| Backend focused ruff | Passed |
| Frontend lint | Passed |
| Frontend build | Passed |
| Frontend targeted Playwright | Passed: `tests/e2e/tutor-workflow.spec.ts` (`2 passed`) |
| In-app browser smoke | Passed: tutor queue/detail and admin SLA card |

## Deploy Evidence

| Repo | Workflow | Run | SHA | Result |
|------|----------|-----|-----|--------|
| `stoa-backend` | Deploy Backend | `27133648881` | `70cb8ae3012c7c7e1fe877f326c1d44b5e34d91b` | Success |
| `stoa-frontend` | Frontend CI | `27133654195` | `b6c0fc4806e51873d72611ac6f6d800bc5f41ba2` | Success |
| `stoa-frontend` | Deploy Frontend | `27133654168` | `b6c0fc4806e51873d72611ac6f6d800bc5f41ba2` | Success |

## Production Smoke

| Check | Result |
|-------|--------|
| `GET https://api.stoaedu.ch/health` | `200`, body `{"status":"ok","version":"0.1.0"}`, request id `eo53hjssZicEPLQ=` |
| `GET https://api.stoaedu.ch/admin/stats` without auth | `401`, request id `eo55kjuJZicEPLQ=` |
| `HEAD https://app.stoaedu.ch/` | `200`, `Last-Modified: Mon, 08 Jun 2026 11:11:16 GMT` |

## Privacy And Safety

- No production teacher reply, report artifact, parent binding, account, legal hold, or support handoff mutation was performed.
- Rich reply payloads are normalized server-side and rendered client-side only through allowlisted React components.
- Unsafe raw HTML and private marker payloads are refused in backend tests and blocked in the frontend composer.

## Residual Gaps

- Content moderation remains future scope.
- Realtime teacher notifications remain future scope.
- Production mutation verification of teacher reply payloads requires a named non-customer teacher-question safe fixture and cleanup path.
- Phase 2 items remain out of scope: Stripe/TWINT, broad multi-subject rollout, student memory, AI teacher assistance tools, WebSocket notifications, mobile/multilingual polish, and direct support-ticket integrations.
