---
phase: 474-deterministic-verification-and-gated-delivery
plan: 93
subsystem: owner-approved-source-handoff
tags: [git-objects, cross-repository, source-authority, formal-admission]

requires:
  - phase: 474-92
    provides: three generic exact-ref formal callers without deployment authority
provides:
  - one canonical non-self-referential B/F/I handoff
  - exact metadata-only publication contract for the owner-approved trust anchor
  - fail-closed P/F/I candidate and two-formal-receipt admission verifier
affects: [474-94, V9QUAL-01, V9QUAL-02]

tech-stack:
  added: []
  patterns:
    - immutable Git object verification with shallow and missing-object rejection
    - direct-child metadata publication without self-serialized publication identity
    - validate-first fixed-pointer semantic reproducibility projection

key-files:
  created:
    - scripts/source_handoff.py
    - schemas/release/source-handoff-v1.schema.json
    - schemas/release/source-handoff-admission-v1.schema.json
    - tests/test_source_handoff.py
    - evidence/phase-474/final-source-handoff.json

key-decisions:
  - "The implementation handoff contains only B/F/I; the owner-supplied publication commit remains the external trust input and is never serialized into itself."
  - "Formal execution candidates use the metadata publication as the backend head, producing P/F/I rather than the pre-publication B/F/I tuple."
  - "Receipt admission proves integrity and semantic reproducibility; Plan 94 must still execute both commands sequentially in the no-host-mount Linux runner and retain that provenance."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 93: Owner-Approved Source Handoff Summary

**One immutable implementation tuple is now the only source set eligible for the two Linux formal runs.**

## Accomplishments

- Sealed backend implementation `17858f892ed60d8e520f1adc136248b05b092f97`, frontend `13c4d1067492eead665999d2b43cd359141a6dd6`, and infrastructure `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6` with exact trees and lock digests.
- Added canonical duplicate/nonfinite-free handoff and admission schemas with closed field, repository-order, production `NOT RUN`, and fixed normalization-pointer contracts.
- Added hardened Git plumbing that disables replacement objects, lazy fetch, ambient Git routing, credentials, and protocols; shallow or incomplete reachable object closures fail closed.
- Restricted the metadata publication to exactly two additions and two ordinary-file modifications; source, lock, workflow, verifier, schema, mode, rename, symlink, gitlink, and extra-path drift are rejected.
- Required admission candidates to be the exact clean P/F/I live state and both formal receipts to be distinct, complete PASS, sequential, non-overlapping, Python 3.12.13, and on one approved Linux platform.
- Preserved source, trees, locks, commands, inputs, Python collection identity, Web artifact identity, counts, results, privacy, and production facts across the two-run projection.

## Task Commits

1. `94efec5` RED — define adversarial source handoff, publication, candidate, and two-run contracts.
2. `17858f8` GREEN — implement the immutable Git handoff and formal admission boundary.

The metadata publication is intentionally not named in its own contents. Its exact commit identity is supplied externally by the owner and verified after this four-path commit exists.

## Verification

- Focused handoff contracts: passed.
- Expanded handoff, formal aggregate, release gate, and all three caller contracts: `221 passed`, `0 failed`.
- Ruff and JSON parsing: passed.
- Shallow repository, missing object, extra path, executable mode, noncanonical/duplicate JSON, wrong tuple, duplicate receipt, overlapping window, non-Linux, non-PASS, and retained semantic drift attacks: rejected.
- Existing Ubuntu 26.04 ARM64 VM has no host source mount and passed both network-none and PID-namespace probes; formal execution itself belongs to Plan 94.
- Provider-hosted workflow execution, production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`.

## Trust Boundary

The handoff and receipts provide deterministic integrity, not third-party non-repudiation against the sole owner. The owner's instruction is the external authorization root. Plan 94 must run the two formal commands as separate sequential processes in the inspected no-host-mount VM and retain a closed execution envelope; copied receipt JSON alone is not accepted as operational proof.

## Remaining Work

- Plan 94 must materialize only P/F/I inside the no-host-mount Linux VM, execute the fixed formal aggregate twice, preserve both raw private receipts plus runner provenance, and admit their stable semantic projection.
- V9QUAL-01 and V9QUAL-02 remain incomplete until that real Linux execution passes twice.

## Self-Check: PASSED

- The implementation commit contains the verifier, schemas, and adversarial tests but no publication output.
- This publication changes only the four declared metadata files and contains no self-referential publication SHA.
- No provider, staging, production, mobile, or native action occurred.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
