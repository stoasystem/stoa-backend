# Phase 82 Live Verification

**Status:** Passed
**Date:** 2026-06-07

## Credential Path

Production smoke used the existing long-lived admin credential path:

```text
AWS Secrets Manager: stoa/production/admin/stoaedu.ad@gmail.com
```

The secret value was consumed by temporary smoke scripts and was not printed, copied into repository files, or committed.

## API Immutable Persistence Smoke

Temporary script:

```text
/private/tmp/stoa_phase82_live_persist_smoke.mjs
```

Executed at `2026-06-07T17:04:58.899Z` against `https://api.stoaedu.ch`.

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| POST | `/auth/login` | 200 | `ematdgbU5icEMqw=` | none recorded; token body intentionally not scanned or printed |
| POST | `/admin/reports/immutable-evidence/status` | 200 | `emauNgb4ZicEMqw=` | none |
| POST | `/admin/reports/immutable-evidence/persist` | 200 | `emauThXE5icENGw=` | none |

Persisted metadata:

```json
{
  "manifest_id": "audit-retention-55f77e9f16a24bae893503ddb8e15610",
  "immutable_ref_id": "immutable-e512057971925618494ffb33",
  "manifest_digest": "sha256:e512057971925618494ffb33ff3b357192582ee4eec30edd8f9a04c73f4b1711",
  "object_digest": "sha256:1fca9ada5b3605db27eaebd3fc9f73718fab841b694d0e0176744a153d2b5f39",
  "item_count": 1,
  "storage_status": "ready",
  "privacy_passed": true
}
```

## DynamoDB Verification

Verified metadata-only manifest reference:

- Status: `persisted`
- Immutable reference matched API response.
- Manifest digest matched API response.
- Object digest matched API response.
- Object key digest present.
- Storage mode: `cdk_managed`
- CDK-managed flag: true
- Audit event count for the manifest partition: 2

No audit rows were deleted.

## S3 Metadata Verification

Verified with `s3api head-object` only. The object payload was not downloaded.

- Content type: `application/vnd.stoa.audit-retention-manifest+json`
- Server-side encryption: `AES256`
- Object Lock mode: `GOVERNANCE`
- Retain-until date present: true
- Version ID present: true
- Object metadata matched immutable ref, manifest id, and manifest digest.

The committed evidence intentionally omits bucket name and object key.

## Browser Smoke

Temporary script:

```text
/private/tmp/stoa_phase82_browser_smoke.mjs
```

Executed at `2026-06-07T17:15:07.428Z` against `https://app.stoaedu.ch/admin/report-operations`.

Result:

```json
{
  "final_url": "https://app.stoaedu.ch/admin/report-operations",
  "immutable_panel_visible": true,
  "release_evidence_selected": true,
  "status_ready_visible": true,
  "cdk_managed_visible": true,
  "blocked_mutations": 0,
  "status_response": 200,
  "privacy_hits": []
}
```

Screenshot retained outside the repo:

```text
/private/tmp/stoa_phase82_browser_smoke.png
```

## Privacy Result

No private marker hits were found in API smoke output, browser status response, or browser page text.

Committed evidence excludes raw object payloads, S3 object keys, presigned URLs, auth tokens, cookies, passwords, AWS secrets, raw report JSON/HTML, and customer report artifacts.
