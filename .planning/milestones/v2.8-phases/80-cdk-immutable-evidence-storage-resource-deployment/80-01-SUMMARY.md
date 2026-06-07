# Phase 80 Summary: CDK Immutable Evidence Storage Resource Deployment

**Status:** Complete
**Completed:** 2026-06-07
**Requirement:** IMSTORE-02

## Delivered

- Added a retained, versioned, Object Lock-enabled immutable evidence metadata bucket to `StoaStorageStack`.
- Configured default S3 Object Lock retention: GOVERNANCE mode for 365 days.
- Added CloudFormation outputs for bucket, prefix, retention mode, and retention days.
- Injected immutable storage runtime settings into `stoa-api`.
- Granted `stoa-api` `s3:GetObject` and `s3:PutObject` on `audit-retention/*`.
- Left `stoa-weekly-report` without immutable storage env vars.
- Deployed through the normal `stoa-infra` GitHub Actions CDK workflow.
- Verified live AWS storage, runtime configuration, and IAM.

## Evidence

- Infra commit: `c3d0d60`
- Deploy workflow run: `27098074719`
- CDK deploy job: `79973842897`
- Backend Lambda dist source tree hash: `661d4e0000ef`

## Acceptance Criteria

- CDK creates the immutable evidence storage resource and injects required backend environment variables: passed.
- API Lambda permissions are scoped to the approved immutable evidence resource/prefix and do not broaden report artifact access: passed.
- CDK diff/deploy evidence, workflow run IDs, commit SHAs, and timestamps are recorded: passed.
- Tests/static checks prove expected stack exports/injected settings and no weakened report bucket privacy: passed.

## Next Phase

Phase 81 enables and verifies backend immutable manifest persistence against the CDK-managed runtime configuration.
