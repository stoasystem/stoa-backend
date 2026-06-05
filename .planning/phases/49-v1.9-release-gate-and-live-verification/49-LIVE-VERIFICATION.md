# Phase 49 Live Verification

**Date:** 2026-06-05
**Status:** Passed
**Production app:** `https://app.stoaedu.ch/admin/report-operations`
**Production API:** `https://api.stoaedu.ch`

## Credential Path

Production smoke used the long-lived secret-backed admin credential path:

```text
AWS Secrets Manager: stoa/production/admin/stoaedu.ad@gmail.com
```

Cognito group verification:

```json
[
  "admins"
]
```

The secret value was used by the smoke script but was not printed, copied into artifacts, or committed.

## API Checks

Executed at `2026-06-05T11:52:56.144Z` with redacted admin user `s***@gmail.com`.

API login:

| Field | Value |
|-------|-------|
| Path | `POST /auth/login` |
| Status | `200` |
| Request ID | `efHH8h_L5icENGw=` |
| Role | `admin` |

Read-only API checks:

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| GET | `/health` | 200 | `efHIegNfZicEMKg=` | none |
| GET | `/admin/reports/recovery-evidence?limit=1` without auth | 401 | `efHIfj9rZicEMTw=` | none |
| GET | `/admin/reports/recovery-evidence?limit=1` with admin auth | 200 | `efHIfhpGZicEMpQ=` | none |
| GET | `/admin/reports/recovery-evidence?limit=101` with admin auth | 422 | `efHIiiW55icEMqw=` | none |
| GET | `/admin/reports/recovery-jobs` with admin auth | 200 | `efHIjiW65icEMqw=` | none |
| GET | `/admin/reports/ops?status=generation_failed&limit=1` with admin auth | 200 | `efHIjjLv5icEMag=` | none |

There were no existing production recovery jobs returned by the list response during this smoke, so the read-only support-package GET was skipped rather than creating a production job.

## Production Browser Smoke

Smoke result:

```json
{
  "finalUrl": "https://app.stoaedu.ch/admin/report-operations",
  "exportPanelVisible": true,
  "retryGenerationVisible": true,
  "supportPackageVisible": false,
  "exportClicked": true,
  "blockedMutations": [],
  "privacyHits": [],
  "mutationPerformed": false
}
```

Captured browser API responses:

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| GET | `/admin/reports/ops?status=email_failed&limit=25` | 200 | `efHJQiXwZicEMqw=` | none |
| GET | `/admin/reports/recovery-jobs` | 200 | `efHJQiXw5icEMqw=` | none |
| GET | `/admin/reports/recovery-evidence?status=email_failed&limit=25` | 200 | `efHJThMS5icEMDA=` | none |

Screenshot:

```text
/private/tmp/stoa-phase49-production-report-operations.png
```

Read-only guarantee:

- Browser routing blocked non-GET `/admin/reports/**` requests.
- No non-GET `/admin/reports/**` request was attempted.
- No preview, resume create, retry, resend, bulk resend, job cancellation, S3 read, S3 write, or report state mutation was performed.

UI availability:

- Production bundle contains `Preview resume`, `Start resume`, `Support package`, `resume/preview`, and `support-package`.
- `supportPackageVisible=false` only because production had no recovery job to select during this read-only smoke.

Privacy guarantee:

- Visible UI text and captured API response bodies were scanned against the denylist.
- No private S3 key, presigned URL, raw report JSON/HTML, artifact payload, or token marker appeared.

## Conclusion

Live verification passed for:

- API health.
- Admin auth gate and request IDs.
- Production UI route load.
- Production bundle support/resume UI markers.
- Metadata-only privacy boundary.
- No production mutation during smoke.

