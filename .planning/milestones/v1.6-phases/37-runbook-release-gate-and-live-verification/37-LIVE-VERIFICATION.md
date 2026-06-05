# Phase 37 Live Verification

**Date:** 2026-06-05
**Status:** Passed

## API Health

Command:

```bash
curl -i -sS https://api.stoaedu.ch/health
```

Result:

```text
HTTP/2 200
apigw-requestid: eddxOg695icEMLA=

{"status":"ok","version":"0.1.0"}
```

## Auth Gate

Command:

```bash
curl -i -sS https://api.stoaedu.ch/admin/reports/recovery-jobs
```

Result:

```text
HTTP/2 401
www-authenticate: Bearer
apigw-requestid: eddxOiDjZicEMog=

{"message":"Unauthorized"}
```

## Production Admin Browser Smoke

Executed in Phase 36 at `2026-06-04T23:51:36Z` using the secret-backed production admin credential path:

```text
AWS Secrets Manager: stoa/production/admin/stoaedu.ad@gmail.com
```

Result:

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

Read-only guarantee:

- The smoke blocked non-GET `/admin/reports/**` requests.
- No retry, resend, bulk resend, job creation, or cancellation was performed.
- No production report was mutated.

Privacy guarantee:

- Visible UI and captured API responses were scanned.
- No private marker was found for `weekly-reports/`, S3 key fields, presigned URL markers, direct S3 URLs, raw report HTML, raw report JSON, or auth tokens.

## Lambda State

| Function | State | LastUpdateStatus | CodeSha256 |
|----------|-------|------------------|------------|
| `stoa-api` | Active | Successful | `xP1TYqxW02AQUo0HN/IZ3rP7rH7Iu4YYLZGYncasxjw=` |
| `stoa-weekly-report` | Active | Successful | `xP1TYqxW02AQUo0HN/IZ3rP7rH7Iu4YYLZGYncasxjw=` |

Both functions use Python 3.12 on arm64 and were updated by backend deploy run `26983049612`.

## CDK Diff

`StoaApiStack` diff with dependency stacks returned 0 stacks with differences.

Stacks checked:

- `StoaAuthStack`
- `StoaDatabaseStack`
- `StoaStorageStack`
- `StoaNotificationStack`
- `StoaApiStack`

## Conclusion

Live verification passed for:

- API health.
- Unauthenticated admin rejection.
- Authenticated production admin browser route.
- Production job/list GET APIs.
- Metadata-only privacy boundary.
- No production mutation during smoke.
- Lambda runtime state.
- Clean CDK diff.
