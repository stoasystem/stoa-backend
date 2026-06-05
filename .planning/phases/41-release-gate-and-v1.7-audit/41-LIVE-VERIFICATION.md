# Phase 41 Live Verification

**Date:** 2026-06-05
**Status:** Passed
**Production app:** `https://app.stoaedu.ch/admin/report-operations`
**Production API:** `https://api.stoaedu.ch`

## Credential Path

Production smoke used the long-lived secret-backed admin credential path:

```text
AWS Secrets Manager: stoa/production/admin/stoaedu.ad@gmail.com
```

Secret metadata check:

| Field | Value |
|-------|-------|
| Name | `stoa/production/admin/stoaedu.ad@gmail.com` |
| ARN | `arn:aws:secretsmanager:eu-central-2:562923011260:secret:stoa/production/admin/stoaedu.ad@gmail.com-GwYGJP` |
| LastChangedDate | `2026-06-05T01:49:15.716000+02:00` |
| LastAccessedDate | `2026-06-05T02:00:00+02:00` |

The secret value was used by the smoke script but was not printed, copied into artifacts, or committed.

## Cognito Group Verification

Command:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-list-groups-for-user \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com \
  --query 'Groups[].GroupName' \
  --output json
```

Result:

```json
[
  "admins"
]
```

## API Checks

Executed at `2026-06-05T09:46:27.235Z` with redacted admin user `s***@gmail.com`.

API login:

| Field | Value |
|-------|-------|
| Path | `POST /auth/login` |
| Status | `200` |
| Request ID | `ee0mMglDZicEJYQ=` |
| Role | `admin` |

Read-only API checks:

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| GET | `/health` | 200 | `ee0mRgcZZicEJ4Q=` | none |
| GET | `/admin/reports/recovery-evidence?limit=1` without auth | 401 | `ee0mSgcaZicEJ4Q=` | none |
| GET | `/admin/reports/recovery-evidence?limit=1` with admin auth | 200 | `ee0mSglK5icEJYQ=` | none |
| GET | `/admin/reports/recovery-evidence?limit=101` with admin auth | 422 | `ee0mTiak5icEJ6g=` | none |

Bounds check:

- `limit=101` was rejected with `422` because the export API maximum is `100`.

Authorization check:

- The unauthenticated export request returned `401`.
- The authenticated admin export request returned `200`.

Privacy denylist checked:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- `presignedUrl`
- `presigned_url`
- `https://s3`
- raw report HTML markers
- raw report JSON markers
- access token, ID token, refresh token markers

Result: no privacy hits.

## Production Browser Smoke

Executed at `2026-06-05T09:46:27.235Z` through Playwright with the real production login page and secret-backed admin credential path.

Smoke result:

```json
{
  "finalUrl": "https://app.stoaedu.ch/admin/report-operations",
  "exportPanelVisible": true,
  "exportClicked": true,
  "blockedMutations": [],
  "privacyHits": [],
  "mutationPerformed": false
}
```

Captured browser API responses:

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| GET | `/admin/reports/recovery-jobs` | 200 | `ee0m7ir85icEJ7A=` | none |
| GET | `/admin/reports/ops?status=email_failed&limit=25` | 200 | `ee0m7hIEZicEKhw=` | none |
| GET | `/admin/reports/recovery-evidence?status=email_failed&limit=25` | 200 | `ee0m_ibVZicEJ6g=` | none |

Screenshot:

```text
/private/tmp/stoa-phase41-production-report-operations.png
```

Read-only guarantee:

- Browser routing blocked non-GET `/admin/reports/**` requests.
- No non-GET `/admin/reports/**` request was attempted.
- No retry, resend, bulk resend, job creation, job cancellation, S3 read, S3 write, or report state mutation was performed.

UI privacy guarantee:

- Visible UI text and captured API response bodies were scanned against the denylist.
- No private S3 key, presigned URL, raw report JSON/HTML, artifact payload, or token marker appeared.

## Conclusion

Live verification passed for:

- API health.
- Unauthenticated admin export rejection.
- Authenticated admin export success.
- Export bounds rejection.
- Request ID capture.
- Cognito `admins` group membership.
- Production UI evidence export panel.
- Metadata-only privacy boundary.
- No production mutation during smoke.

