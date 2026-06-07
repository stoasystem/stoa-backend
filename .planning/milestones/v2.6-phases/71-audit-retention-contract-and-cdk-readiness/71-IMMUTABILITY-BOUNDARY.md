# Phase 71 Immutability Boundary

**Status:** Complete
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

## Operator Language

Use `sealed metadata manifest` or `retention-ready manifest` for v2.6 output. Do not use `immutable audit log`, `WORM evidence`, `legal hold`, or `compliance retained` unless a future release deploys and verifies the CDK-managed storage controls that make those claims true.

## Refused Actions

v2.6 APIs and UI must refuse or omit:

- Audit row deletion, expiry, or retention shortening.
- Direct Object Lock, legal hold, or WORM writes.
- External support-system retention writes.
- Any request that asks to include raw report artifacts or private storage identifiers in retained evidence.

## Safety Rules

- No manual AWS console changes.
- No destructive audit expiry/deletion behavior in v2.6.
- No raw report artifact retention in manifests.
- No new storage resource without CDK source-of-truth change and release evidence.

## Future WORM Path

If compliance-grade retention is approved later, it should be implemented as a separate CDK-owned storage design with Object Lock or equivalent infrastructure controls, explicit retention-period ownership, release evidence, and rollback/escape-hatch analysis. Phase 72 and Phase 73 should keep their contracts compatible with that future path by using stable manifest IDs and digest metadata.
