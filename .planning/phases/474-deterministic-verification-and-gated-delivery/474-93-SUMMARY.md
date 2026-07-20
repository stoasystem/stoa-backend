---
phase: 474-deterministic-verification-and-gated-delivery
plan: 93
subsystem: owner-approved-source-handoff
tags: [git-objects, cross-repository, source-authority, formal-admission, superseding-publication]

requires:
  - phase: 474-92
    provides: three generic exact-ref formal callers without deployment authority
provides:
  - one canonical non-self-referential B/F/I handoff after both snapshot-layout repairs
  - exact metadata-only publication contract for the final owner-approved trust anchor
  - fail-closed P/F/I candidate and two-formal-receipt admission verifier
affects: [474-94, V9QUAL-01, V9QUAL-02]

key-decisions:
  - "Publications f9f6b2b4 and de52a2ee are historical rejected evidence; neither contributes a PASS run."
  - "The final implementation resolves marker-validated frontend and infra roots in both local stoa-* and materialized short-name layouts, rejecting missing or ambiguous candidates."
  - "The handoff contains only B/F/I; the final publication commit remains the owner-supplied external trust input and is never serialized into itself."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 93: Final Owner-Approved Source Handoff Summary

**The exact source handoff was reissued only after the repaired materialized layout passed the complete strict Linux suite.**

## Accomplishments

- Retained both failed real Linux attempts as rejected history: each Web child passed, while its Python child exposed a distinct hard-coded snapshot-layout assumption.
- Added red regressions for the materialized `backend/frontend/infra` layout and ambiguous marker-valid siblings.
- Replaced hard-coded default sibling names with one marker- and lock-validated exact match across local `stoa-*` and formal short-name layouts.
- Sealed final backend implementation `6b3b464af7f4a37f187d9d75dea6b62ad0439624`, unchanged frontend `13c4d1067492eead665999d2b43cd359141a6dd6`, and unchanged infrastructure `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6`.
- Retained canonical A/A/M/M publication, complete object-closure, P/F/I admission, fixed-pointer projection, and production `NOT RUN` controls.

## Relevant Commits

1. `16d8219` RED — reproduce the formal snapshot root failure.
2. `6cbaa87` RED — reject ambiguous marker-valid snapshot roots.
3. `ccc53f9` GREEN — resolve exact default repositories in both supported layouts.
4. `6b3b464` REISSUE BASE — remove the rejected handoff artifacts before final issuance.

The final publication is intentionally not named in its own contents. Its full SHA is supplied externally by the owner after this four-path commit exists.

## Verification

- Targeted snapshot-root regressions: `2 passed`, `0 failed`.
- Expanded dependency, handoff, formal aggregate, release gate, and three-caller regression: `246 passed`, `0 failed`.
- Materialized Ubuntu ARM64 strict full-suite preflight: `2344 passed`, `0 failed`, `0 skipped`, `0 xfail`, `0 xpass`.
- Ruff, canonical handoff issuance, full bundle/object closure, clean exact checkouts, Linux network namespace, and no-host-mount probes: passed.
- Historical publications `f9f6b2b4a83686f14f5ba88dbf388f6260f0df0a` and `de52a2ee42b5017f46849c2041da75c1b0026963`: rejected and not counted.
- Production infrastructure, deploy, smoke, rollback, provider workflow, staging, mobile, and native: exact `NOT RUN`.

## Remaining Work

- Plan 94 must use only the final publication plus unchanged F/I, run the full formal aggregate twice from scratch, and preserve both raw receipts, admission, and no-host-mount execution envelope.
- V9QUAL-01 and V9QUAL-02 remain incomplete until both final-source Linux runs pass.

## Self-Check: PASSED

- The final implementation base contains no handoff or Plan 93 summary, so publication remains direct and non-circular.
- This publication changes only the declared four ordinary metadata files.
- Neither prior failed formal receipt is labeled or counted as PASS.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
