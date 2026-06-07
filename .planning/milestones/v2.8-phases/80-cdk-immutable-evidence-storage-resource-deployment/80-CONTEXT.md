# Phase 80 Context: CDK Immutable Evidence Storage Resource Deployment

**Milestone:** v2.8 CDK-Managed Immutable Evidence Storage Deployment
**Requirement:** IMSTORE-02
**Status:** Complete
**Date:** 2026-06-07

## Starting Point

Phase 79 selected a dedicated CDK-managed immutable evidence S3 bucket in `StoaStorageStack` and API-only wiring in `StoaApiStack`.

The backend already contained v2.7 fail-closed immutable manifest persistence code. Before Phase 80, production Lambda configuration did not provide the immutable storage mode/resource/prefix settings, so production status remained not configured.

## Safety Boundary

- No AWS console changes.
- No production audit row deletion.
- No customer report artifact mutation.
- No raw report artifacts, raw report JSON/HTML, presigned URLs, S3 object keys, auth tokens, cookies, passwords, or AWS secrets in committed evidence.
- Object persistence remains scoped to metadata-only audit retention manifests.
- The weekly report Lambda must not receive immutable storage environment variables or immutable bucket permissions.

## Repositories

- Backend planning repo: `stoa-backend`
- Infrastructure repo: `stoa-infra`

## Target Resources

- Stack: `StoaStorageStack`
- Construct: `StoaImmutableEvidenceBucket`
- Prefix: redacted in committed evidence except for the approved logical prefix `audit-retention/`
- Retention: S3 Object Lock default retention, GOVERNANCE mode, 365 days
- Removal policy: `RETAIN`
- API permissions: `s3:GetObject`, `s3:PutObject` on the immutable evidence prefix only
