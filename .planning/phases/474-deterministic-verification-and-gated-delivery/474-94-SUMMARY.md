---
phase: 474-deterministic-verification-and-gated-delivery
plan: 94
subsystem: linux-formal-admission
tags: [linux, hermetic, no-host-mount, two-run, source-admission]

requires:
  - phase: 474-93
    provides: final owner-approved P/F/I publication and admission verifier
provides:
  - two sequential complete Linux formal PASS receipts for exact P/F/I
  - byte-stable machine admission from an independent fresh exact-source checkout
  - canonical no-host-mount execution envelope with production kept NOT RUN
affects: [V9QUAL-01, V9QUAL-02]

key-decisions:
  - "Only publication fe467c5e4bdcce55863f62a0e7ffe26ca2c88ca0 and its handoff-bound F/I commits contribute PASS evidence."
  - "The two formal commands are separate sequential processes; distinct raw receipts normalize to one fixed retained semantic digest."
  - "The evidence is owner-operated local-VM provenance and does not claim third-party non-repudiation."

requirements-completed: [V9QUAL-01, V9QUAL-02]
completed: 2026-07-20
---

# Phase 474 Plan 94: Two Linux Formal Runs And Sealed Admission Summary

**V9QUAL-01 and V9QUAL-02 now have two complete, sequential, machine-admitted Linux PASS runs for one exact cross-repository source tuple.**

## Accomplishments

- Materialized complete Git bundles into an Ubuntu 26.04 ARM64 Lima VM configured with `mounts: null`; proved no 9p, virtiofs, sshfs, host source mount, shallow repository, missing object, source drift, or namespace failure.
- Ran the formal aggregate twice as separate processes on Python 3.12.13 and uv 0.11.16, starting run 2 only after run 1 ended.
- Each formal run passed both Python fresh environments with `2344/2344` nodes and Web with `5/5` fixed steps; skip, xfail, xpass, failed, error, and omitted counts are all zero.
- Preserved different raw receipt identities while proving identical retained semantics at `7915ab0b1aa25c3583c9f8018b513a363ace515a0e1daa3b2e02c1d2640b3ebe`.
- Re-ran admission in a second fresh exact P/F/I checkout and obtained a byte-identical admission artifact.
- Kept infrastructure mutation, deployment, smoke, rollback, provider workflow, staging, mobile, and native exact `NOT RUN`.

## Exact Source

- Publication P: `fe467c5e4bdcce55863f62a0e7ffe26ca2c88ca0`
- Implementation B: `6b3b464af7f4a37f187d9d75dea6b62ad0439624`
- Frontend F: `13c4d1067492eead665999d2b43cd359141a6dd6`
- Infrastructure I: `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6`
- Candidate identity: `b29c8138222a3bfb2351e1f095c34f26a88e2c44a9eedbb835e54981329e25ee`

## Formal Results

| Run | Receipt window (UTC) | Python | Web | Raw receipt SHA-256 | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | 08:06:28.101351–08:10:25.403947 | 2 × 2344 PASS | 5 PASS | `18478240144bb9a9a94df796c10e50b604eb2e6bd71a538fc5fb40ea754f4b34` | PASS |
| 2 | 08:11:19.869426–08:15:17.723800 | 2 × 2344 PASS | 5 PASS | `d2a7186c33293de9ea88905d83a2bc78561fe78ee51ed7bd040bfd7e88ce2e8b` | PASS |

Both Python runs use fixed clocks `2026-07-01T12:00:00Z` and `2035-01-15T12:00:00Z`, seed `4740718`, and collection identity `44f385468c352ab8c42d26bd1b38de296dc03ce37e87f35b5f69ba32a9c7e3ac`.

## Evidence

- `evidence/phase-474/linux-formal-run-1.json` — raw run 1 file SHA-256 `ba84a54373d992b4eae0bcd8b84ed9a08122d17f76b40bae3bbebe65cd5eaf81`.
- `evidence/phase-474/linux-formal-run-2.json` — raw run 2 file SHA-256 `b5d42750a41dd5b805e897e855c2462b1be0edad840492003fd0ab6348c693cc`.
- `evidence/phase-474/linux-formal-admission.json` — PASS admission file SHA-256 `847aef6d0fc0268cd67765f03a72c9bf60a7078e7679595cc1f3bdfefac4691c`.
- `evidence/phase-474/linux-formal-execution-envelope.json` — canonical source, environment, isolation, sequence, and digest envelope.

## Verification

- Materialized strict Linux preflight before final publication: `2344 passed`, `0 failed`, `0 skipped`, `0 xfail`, `0 xpass`.
- Formal run 1: aggregate `COMPLETE_PASS`, Python `COMPLETE_PASS`, Web `COMPLETE_PASS`.
- Formal run 2: aggregate `COMPLETE_PASS`, Python `COMPLETE_PASS`, Web `COMPLETE_PASS`.
- P-owned admission: PASS; receipt windows non-overlapping; raw digests distinct; stable projections identical.
- Fresh exact P/F/I revalidation: admission bytes and SHA-256 identical.
- Canonical evidence cross-binding and later-HEAD publication revalidation: passed.
- Expanded local formal, handoff, dependency, and caller regression: `246 passed`, `0 failed`.

## Deviations Resolved

- Two earlier publications were rejected after real Linux execution exposed separate local-name assumptions in complete-suite tests. Both were repaired with red regressions, excluded from PASS credit, and superseded before these runs.
- One concurrent local timeout-contract failure was reproduced alone and passed; it came from accidentally overlapping two local regression invocations, not from the final sequential formal runs.

## Self-Check: PASSED

- Two complete independent process executions exist and are sequential.
- Both raw receipts validate against the exact clean candidate and fixed formal graph.
- Admission is reproducible from a fresh exact-source checkout.
- Production and every excluded external operation remain `NOT RUN`.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
