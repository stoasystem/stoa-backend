---
phase: 474-deterministic-verification-and-gated-delivery
plan: 93
subsystem: owner-approved-source-handoff
tags: [git-objects, cross-repository, source-authority, formal-admission, superseding-publication]

requires:
  - phase: 474-92
    provides: three generic exact-ref formal callers without deployment authority
provides:
  - one canonical non-self-referential B/F/I handoff after real snapshot-path repair
  - exact metadata-only publication contract for the replacement owner-approved trust anchor
  - fail-closed P/F/I candidate and two-formal-receipt admission verifier
affects: [474-94, V9QUAL-01, V9QUAL-02]

key-decisions:
  - "The first publication was rejected after its real Linux Python child exposed a materialized-snapshot Web-root path failure; it is historical failure evidence, not an admissible PASS source."
  - "The replacement implementation contains the portable test-root repair and removes the rejected publication artifacts before issuing a new non-self-referential handoff."
  - "The handoff contains only B/F/I; the replacement publication commit remains the owner-supplied external trust input and is never serialized into itself."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 93: Replacement Owner-Approved Source Handoff Summary

**The exact source handoff was reissued only after the first real Linux formal attempt exposed and repaired a snapshot-layout gap.**

## Accomplishments

- Preserved the historical publication `f9f6b2b4a83686f14f5ba88dbf388f6260f0df0a` as rejected evidence: its Python child failed policy validation and it is not counted toward V9QUAL-01 or V9QUAL-02.
- Repaired `tests/test_dependency_policy.py` so the complete suite resolves exactly one marker-validated Web root in both local `stoa-frontend` and formal snapshot `frontend` layouts.
- Sealed replacement backend implementation `2726a499e4a6b97199bdbf1f6d19cf037baa62a2`, unchanged frontend `13c4d1067492eead665999d2b43cd359141a6dd6`, and unchanged infrastructure `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6`.
- Retained the canonical, non-self-referential A/A/M/M publication, complete object-closure, P/F/I admission, fixed-pointer projection, and production `NOT RUN` controls.

## Relevant Commits

1. `94efec5` RED — define adversarial source handoff and admission contracts.
2. `17858f8` GREEN — implement immutable handoff and admission verification.
3. `5b6b8ac` GAP FIX — resolve the authoritative Web test root in formal snapshots.
4. `2726a49` REISSUE BASE — remove rejected publication artifacts before replacement issuance.

The replacement publication is intentionally not named in its own contents. Its full SHA is supplied externally by the owner after this four-path commit exists.

## Verification

- Dependency-policy regression: `24 passed`, `0 failed`.
- Expanded dependency, handoff, formal aggregate, release gate, and three-caller regression: `245 passed`, `0 failed`.
- Ruff, JSON parsing, canonical handoff issuance, shallow/missing object denial, exact raw publication diff, and clean candidate checks: passed.
- Historical Linux attempt: Web child PASS; Python child policy-rejected because the old test constant selected a nonexistent snapshot sibling. This failure is retained and not promoted.
- Production infrastructure, deploy, smoke, rollback, provider workflow, staging, mobile, and native: exact `NOT RUN`.

## Remaining Work

- Plan 94 must use only the replacement publication plus unchanged F/I, run the full formal aggregate twice from scratch, and preserve both raw receipts, admission, and no-host-mount execution envelope.
- V9QUAL-01 and V9QUAL-02 remain incomplete until both replacement-source Linux runs pass.

## Self-Check: PASSED

- The replacement implementation base contains no handoff or Plan 93 summary, so the new publication remains direct and non-circular.
- This replacement publication changes only the declared four ordinary metadata files.
- The prior failed formal receipt is not labeled or counted as PASS.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
