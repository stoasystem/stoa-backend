# Phase 80 Deploy Evidence

**Status:** Complete
**Date:** 2026-06-07

## Infra Commit

- Repository: `stoasystem/stoa-infra`
- Branch: `main`
- Commit: `c3d0d60`
- Message: `feat: add immutable evidence storage bucket`

Changed files:

- `app.py`
- `stacks/api_stack.py`
- `stacks/storage_stack.py`

## Local Validation

- `uv run python -m py_compile app.py stacks/storage_stack.py stacks/api_stack.py`: passed.
- `PYTHONPATH=src .venv/bin/python scripts/build_lambda_dist.py --skip-install`: passed.
- Lambda dist provenance:
  - Backend commit SHA: `a7d31ea788d5a155b2f0472c20022b770e3aabde`
  - Source tree hash: `661d4e0000ef`
- `uv run cdk synth`: passed.
- `uv run cdk diff StoaStorageStack StoaApiStack --profile stoa-prod-admin --output /private/tmp/stoa_phase80_cdk_out`: passed.

## CDK Diff Classification

Expected differences:

- `StoaStorageStack`
  - Added one S3 bucket for immutable evidence metadata.
  - Added bucket policy denying non-SSL access.
  - Added access-log delivery permission for the existing access logs bucket under `immutable-evidence/`.
  - Added outputs for immutable evidence bucket, prefix, Object Lock mode, and retention days.
- `StoaApiStack`
  - Added API Lambda environment variables for immutable storage mode, managed flag, resource, and prefix.
  - Added API Lambda IAM permissions: `s3:GetObject`, `s3:PutObject` on `audit-retention/*`.
  - Lambda code asset key changed because the backend Lambda dist was rebuilt.
  - Weekly report Lambda code asset key changed with the shared rebuilt package, but it did not receive immutable storage environment variables.

No immutable evidence `s3:DeleteObject` permission appeared in the synthesized immutable prefix statement.

## GitHub Actions Deployment

- Workflow: `Deploy Infrastructure`
- Run ID: `27098074719`
- URL: `https://github.com/stoasystem/stoa-infra/actions/runs/27098074719`
- Trigger: push to `main`
- Head SHA: `c3d0d6041584bb482ea6b041726d9b6e06aa4263`
- Created: `2026-06-07T16:21:38Z`
- CDK Diff job: success, job ID `79973726489`
- CDK Deploy job: success, job ID `79973842897`

## Live AWS Verification

Verified after workflow success:

- `StoaStorageStack` immutable outputs exist.
- Bucket versioning: `Enabled`.
- Object Lock: `Enabled`.
- Default retention: `GOVERNANCE`, `365` days.
- Public access block: all four controls enabled.
- Server-side encryption: AES256.
- Server access logging: enabled to the existing access logs bucket under `immutable-evidence/`.
- `stoa-api` Lambda immutable storage environment variables are present.
- `stoa-weekly-report` Lambda has no immutable storage environment variables.
- API role inline immutable prefix statement has only:
  - `s3:GetObject`
  - `s3:PutObject`

Private resource identifiers from live AWS output are intentionally not committed here unless already part of public CDK code or approved logical prefixes.
