# Phase 77 UI Spec: Admin Immutable Evidence And Legal Hold UI

**Phase:** 77
**Status:** Complete

## Audience

Admin/operators using `/admin/report-operations` during report operations support and audit retention workflows.

## Experience Goals

- Make immutable evidence status inspectable without implying WORM/Object Lock is configured.
- Let operators run backend legal hold metadata workflows with explicit reasons.
- Preserve dense, scan-friendly operational UI conventions already used on report operations.
- Keep metadata-only privacy boundaries visible and testable.

## Controls

- Check immutable status.
- Persist manifest.
- Check legal hold.
- Apply hold.
- Release hold.
- Copy JSON.
- Download JSON.

## States

- `not_configured`: CDK-managed immutable storage is absent.
- `persisted`: metadata reference persisted when backend config is ready.
- `active`: legal hold metadata active.
- `released`: legal hold metadata released.
- `refused`: backend refused unsupported or unsafe request.

## Privacy Requirements

The UI must not render private report artifact markers, S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, cookies, passwords, AWS secrets, backend storage resource names, bucket names, object keys, or raw immutable object payloads.

## Verification

Use frontend lint/build and the existing admin report operations Playwright spec with immutable/legal-hold route mocks and body-level privacy denylist assertions.
