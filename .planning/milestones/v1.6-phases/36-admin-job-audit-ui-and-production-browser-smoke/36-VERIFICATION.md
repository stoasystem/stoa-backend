# Phase 36 Verification

**Date:** 2026-06-05
**Status:** Passed

## Passed

```bash
npm run build
```

Result:

```text
tsc and Vite build passed.
```

```bash
npm run lint
```

Result:

```text
eslint passed.
```

```bash
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result:

```text
1 passed.
```

## Browser Smoke

Local Playwright e2e exercised the admin report operations route and verified no private report artifact markers were rendered. An additional in-app browser smoke attempt through the Node REPL was blocked by macOS sandbox permissions when launching Chromium.

## Production Admin Setup

Follow-up check on 2026-06-05 found that production did not yet have a configured admin account usable for browser smoke. Opening `https://app.stoaedu.ch/admin/report-operations` redirected to `https://app.stoaedu.ch/login` with no current admin session.

The formal setup path is documented in `36-PRODUCTION-ADMIN-SETUP.md`, and `scripts/provision_production_admin.py` provisions all required auth records:

- Cognito user in user pool `eu-central-2_Ss93YQzjJ`
- Cognito `admins` group membership
- DynamoDB `stoa-main` profile with `role = admin`

Provisioning evidence:

- Admin email: `stoaedu.ad@gmail.com`
- Secret-backed credential path: AWS Secrets Manager `stoa/production/admin/stoaedu.ad@gmail.com`
- Provisioning result: `cognito_user=created`, `cognito_group=ensured`, `dynamodb_profile=created`
- Password and tokens were not printed or committed.

## Production Read-Only Browser Smoke

Executed: `2026-06-04T23:51:36Z` (`2026-06-05` local)

Deploy evidence:

- Backend deploy run: `26983049612`
- Backend commit: `7aeb6d4a369796b1244481373c52a0449caacab7`
- Backend deploy job: build Lambda package, verify dist manifest, dry-run Lambda updates, update `stoa-api` and `stoa-weekly-report`, wait for update.
- Frontend deploy run: `26983049968`
- Frontend commit: `b8af433d7dc6f598fef1c142b960cd504c17b2f4`
- Frontend deploy job: production build, lint, S3 sync, no-cache `index.html`, CloudFront invalidation.

Smoke result:

```json
{
  "finalUrl": "https://app.stoaedu.ch/admin/report-operations",
  "titleVisible": true,
  "asyncPanelVisible": true,
  "apiResponses": [
    {
      "method": "GET",
      "path": "/admin/reports/recovery-jobs",
      "status": 200,
      "requestId": "edddVjU3ZicEPsA="
    },
    {
      "method": "GET",
      "path": "/admin/reports/ops?status=email_failed&limit=25",
      "status": 200,
      "requestId": "edddVg3k5icEPfQ="
    }
  ],
  "blockedMutations": [],
  "privacyHits": [],
  "mutationPerformed": false
}
```

Read-only guard:

- The smoke intercepted `/admin/reports/**` and aborted any non-GET request.
- No retry, resend, start-job, bulk-resend, or cancel action was performed.
- No mutation request was observed.

Privacy assertions:

- Visible UI and captured admin report API responses were scanned for private artifact markers.
- No `weekly-reports/`, private S3 key fields, presigned URL markers, direct S3 URL markers, raw report HTML, or raw report JSON markers were found.
