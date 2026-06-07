# Phase 74 Release Gate

**Status:** passed
**Created:** 2026-06-07

## Commits

| Component | Commit | Notes |
|-----------|--------|-------|
| Backend | `fc53e6ef919537f9c86548856f3643f935ba915b` | Phase 71-73 backend/planning; deployed by backend workflow. |
| Frontend | `cc31d0cf2154b5913fc4b855a835d129f30eb861` | Phase 73 audit retention admin UI; deployed by frontend workflow. |

## Local Quality Gates

| Gate | Result | Notes |
|------|--------|-------|
| Backend ruff | passed | `.venv/bin/python -m ruff check src/stoa/services/report_audit_retention_service.py src/stoa/services/support_handoff_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py` |
| Backend pytest | passed | `20 passed, 55 deselected` for `audit_retention or support_handoff or release_evidence or recovery_evidence`. |
| Lambda dist verify | passed | `source_git_sha=fc53e6ef...`, `source_tree_hash=7a7ef460...`, runtime `python3.12`, arm64. |
| Frontend lint | passed | `npm run lint`. |
| Frontend build | passed | `npm run build`; existing Vite chunk-size warning remains. |
| Frontend Playwright | passed | `npx playwright test tests/e2e/admin-report-operations.spec.ts`. |

## GitHub Actions

| Component | Workflow | Run | Job | Result | Completed |
|-----------|----------|-----|-----|--------|-----------|
| Backend | Deploy Backend | `27093874464` | `79962316337` | success | 2026-06-07T13:27:00Z |
| Frontend | Frontend CI | `27093874547` | `79962316530` | success | 2026-06-07T13:26:50Z |
| Frontend | Deploy Frontend | `27093874542` | `79962316552` | success | 2026-06-07T13:27:07Z |

Links:

- Backend deploy: `https://github.com/stoasystem/stoa-backend/actions/runs/27093874464`
- Frontend CI: `https://github.com/stoasystem/stoa-frontend/actions/runs/27093874547`
- Frontend deploy: `https://github.com/stoasystem/stoa-frontend/actions/runs/27093874542`

## Lambda Runtime

| Function | State | Last update | Last modified | CodeSha256 | Runtime | Arch |
|----------|-------|-------------|---------------|------------|---------|------|
| `stoa-api` | Active | Successful | 2026-06-07T13:26:47.000+0000 | `jKW1U8+onmahmmZHXKI3XEVoGXaZO/PKZbUxPoRPO5c=` | python3.12 | arm64 |
| `stoa-weekly-report` | Active | Successful | 2026-06-07T13:26:54.000+0000 | `jKW1U8+onmahmmZHXKI3XEVoGXaZO/PKZbUxPoRPO5c=` | python3.12 | arm64 |

## CDK Diff

`uv run cdk diff --profile stoa-prod-admin --output /private/tmp/stoa_phase74_cdk_out` completed successfully.

Classification:

- No differences in `StoaAuthStack`, `StoaDatabaseStack`, `StoaStorageStack`, `StoaNotificationStack`, `StoaAiStack`, `StoaMonitoringStack`, or `StoaFrontendStack`.
- `StoaApiStack` shows expected Lambda `Code.S3Key` drift for `StoaApiFunction` and `StoaWeeklyReportFunction` only.
- No new WORM/Object Lock/legal hold storage resources, audit deletion resources, external support writes, or broad S3 permissions were introduced.

## Result

Release gate passed.
