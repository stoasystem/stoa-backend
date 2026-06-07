# Phase 88 Live Verification: v2.9 Governance Production Closeout

**Verified:** 2026-06-07  
**Mode:** Production read-only verification

## Deployment Evidence

Backend:

- Repository: `stoasystem/stoa-backend`
- Branch: `main`
- Head SHA: `76a75030fbf6670962a7216018d163633bc6cc03`
- Workflow: `Deploy Backend`
- Run ID: `27105695299`
- Result: `completed / success`
- URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27105695299`

Frontend:

- Repository: `stoasystem/stoa-frontend`
- Branch: `main`
- Head SHA: `b88c673bd66598adfd3142011c56327df4617b56`
- Workflow: `Frontend CI`
- Run ID: `27105696540`
- Result: `completed / success`
- URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27105696540`

Frontend deploy:

- Workflow: `Deploy Frontend`
- Run ID: `27105696551`
- Result: `completed / success`
- URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27105696551`

## Lambda Runtime State

Read-only AWS inspection of `stoa-api`:

```json
{
  "FunctionName": "stoa-api",
  "Runtime": "python3.12",
  "LastModified": "2026-06-07T21:44:40.000+0000",
  "State": "Active",
  "LastUpdateStatus": "Successful",
  "CodeSha256": "LsaMnwUHrDGyHfQ0c46bdCI9CySI5rj/5kdZlDD3eAM=",
  "Version": "$LATEST"
}
```

## API Smoke

Script: `scripts/retention_governance_production_smoke.mjs`  
Evidence file: `/private/tmp/stoa_phase88_governance_api_smoke.json`

Sanitized request evidence:

| Check | Method | Path | Status | Request ID |
|-------|--------|------|--------|------------|
| Health | GET | `/health` | 200 | `enEe3jBS5icENGw=` |
| Admin denial | POST | `/admin/reports/retention-governance/status` | 401 | `enEe4gIRZicEMog=` |
| Admin login | POST | `/auth/login` | 200 | `enEe4hMMZicEMqw=` |
| Governance status | POST | `/admin/reports/retention-governance/status` | 200 | `enEe8gItZicEMpQ=` |
| Legal-hold status | POST | `/admin/reports/legal-holds/status` | 200 | `enEe9gIYZicEMog=` |

API smoke result:

- `mutationAttempted`: `false`
- `authorizationPassed`: `true`
- `statusPassed`: `true`
- `privacyPassed`: `true`
- Immutable storage public status: `ready`, `cdk_managed=true`, `resource_configured=true`, `prefix_configured=true`
- Retention approval state for `retention-policy-v1`: `not_requested`
- Legal-hold status for synthetic release evidence reference: `none`

## Browser Smoke

Script: `/private/tmp/stoa_phase88_browser_smoke.mjs`  
Evidence file: `/private/tmp/stoa_phase88_browser_smoke.json`

Production route verified:

- `https://app.stoaedu.ch/admin/report-operations`

Visible controls:

- Retention governance panel: visible
- Check governance: visible
- Record approval: visible
- Check legal hold: visible
- Record review: visible

Browser smoke result:

- `mutationAttempted`: `false`
- `blockedMutations`: `[]`
- `privacyPassed`: `true`
- `privacyHits`: `[]`
- `browserSmokePassed`: `true`

## Safety Notes

- The API smoke deliberately called only status/read endpoints after login.
- The browser smoke verified production controls without clicking approval, review, apply-hold, release-hold, manifest-persist, or other write controls.
- No production customer report artifact was mutated.
- No audit row or immutable evidence object was deleted.
- No legal/compliance approval was fabricated. Formal approval of retention policy and operating procedure remains an external business/legal activity.

