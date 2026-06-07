# Phase 71 Immutability Boundary

**Status:** Planned
**Created:** 2026-06-07

## Boundary Definitions

| Layer | Meaning | v2.6 Position |
|-------|---------|---------------|
| Application append-only audit | Backend refuses mutation of historical audit rows by convention/service behavior. | Existing baseline. |
| Retention manifest | Metadata-only digest of selected audit evidence with hashes/counts/status. | In scope for v2.6. |
| Immutable/WORM storage | Infrastructure-enforced retention where stored objects cannot be overwritten/deleted before retention expiry. | Future scope unless Phase 71/CDK explicitly approves a resource path. |
| Legal hold | Compliance/operations workflow preventing expiry/deletion while hold is active. | Future scope. |

## Claims Allowed In v2.6

Allowed:

- Metadata-only audit retention readiness.
- Retention manifest generation.
- Drift-detection metadata for selected audit evidence.
- CDK readiness decision for future immutable storage.

Not allowed without deployed evidence:

- Compliance-grade WORM audit storage is active.
- Legal hold is active.
- Existing audit rows are immutable under infrastructure controls.

## Safety Rules

- No manual AWS console changes.
- No destructive audit expiry/deletion behavior in v2.6.
- No raw report artifact retention in manifests.
- No new storage resource without CDK source-of-truth change and release evidence.
