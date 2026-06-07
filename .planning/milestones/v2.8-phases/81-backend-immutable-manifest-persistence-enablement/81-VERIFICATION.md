# Phase 81 Verification

**Status:** Passed
**Date:** 2026-06-07

## Code Coverage Added

Added tests in `tests/test_admin_report_ops.py`:

- `test_immutable_storage_status_reads_cdk_env_without_leaking_resource`
  - Proves uppercase CDK-injected environment variables bind into `Settings`.
  - Proves `_immutable_storage_status()` changes to `ready`.
  - Proves public status exposes only booleans/status and does not expose resource or prefix values.
- `test_immutable_manifest_persistence_refuses_duplicate_reference`
  - Proves duplicate/reference-exists behavior refuses persistence.
  - Proves the immutable object writer is not called after duplicate reference refusal.
  - Proves the refusal is audited and does not expose private storage identifiers.

Existing focused tests continue to cover:

- Missing CDK config refusal.
- Configured persistence path.
- Object-write failure handling.
- Create-only S3 writer semantics with `IfNoneMatch="*"`.
- Object byte digest metadata.
- Privacy denylist checks.
- Legal hold status/apply behavior.

## Local Commands

| Command | Result |
|---------|--------|
| `uv run pytest tests/test_admin_report_ops.py -k "immutable or legal_hold"` | Passed: 13 selected tests |
| `uv run pytest tests/test_admin_report_ops.py` | Passed: 88 tests |
| `uv run ruff check tests/test_admin_report_ops.py src/stoa/services/report_audit_retention_service.py src/stoa/routers/admin.py src/stoa/config.py` | Passed |

The first non-escalated pytest attempt failed before test execution because the sandbox blocked access to the shared `uv` cache. The same command passed with approved cache access.

## Production Read-Only Smoke

Temporary script: `/private/tmp/stoa_phase81_prod_smoke.mjs`

Credential path:

- AWS Secrets Manager: `stoa/production/admin/stoaedu.ad@gmail.com`
- Secret value was consumed by the temporary script and was not printed, copied into repo files, or committed.

Executed at `2026-06-07T16:54:00.133Z` against `https://api.stoaedu.ch`.

| Method | Path | Status | Request ID | Privacy hits |
|--------|------|--------|------------|--------------|
| POST | `/auth/login` | 200 | `emZGchVJ5icEPgQ=` | none recorded; token body intentionally not scanned or printed |
| POST | `/admin/reports/immutable-evidence/status` | 200 | `emZGhjjuZicEP2w=` | none |

Immutable storage public status:

```json
{
  "status": "ready",
  "mode": "cdk_managed",
  "cdk_managed": true,
  "resource_configured": true,
  "prefix_configured": true,
  "missing": []
}
```

Smoke result:

- Privacy passed: true.
- Mutation performed: false.
- Resource value and prefix value were not exposed by the API status response.

## Residual Risk

Phase 82 must execute the one approved metadata-only production persistence smoke and verify the created immutable object/version/retention evidence.
