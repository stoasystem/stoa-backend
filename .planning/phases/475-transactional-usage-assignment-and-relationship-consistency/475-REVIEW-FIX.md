---
phase: 475
fixed_at: "2026-07-23T11:30:27Z"
review_path: ".planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-REVIEW.md"
iteration: 2
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 475: Code Review Fix Report

**Fixed at:** 2026-07-23T11:30:27Z
**Source review:** `.planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-REVIEW.md`
**Iteration:** 2

**Summary:**

- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Expired invocation leases can call the provider twice

**Files modified:** `src/stoa/db/repositories/question_submission_repo.py`, `src/stoa/routers/questions.py`, `tests/test_phase475_question_admission.py`, `tests/test_phase475_question_effect_recovery.py`
**Commit:** `ea70f59`
**Status:** fixed: requires human verification
**Applied fix:** An expired `invoking` lease is no longer transferred to a new provider caller. The repository atomically proves the exact expired owner/lease and terminalizes the ambiguous effect; replay then uses the existing terminal-proof reconciliation path to fail the command, mark the question failed, and reverse admission exactly once. Stable replay performs no provider or transaction work, while a new idempotency key can submit a new question. This deliberately provides terminal convergence, provider invocation at-most-once, and exact-once compensation; it cannot recover an external answer that succeeded before the worker crashed and may therefore discard that answer.
**Verification:** The crash-after-provider-before-receipt test first reproduced the ambiguity and now passes with one provider call, terminal proof, exact-once reversal, stable replay, and successful fresh resubmission. The related question suites passed 109 tests; Ruff, `git diff --check`, and the exact 22-file mypy command passed.

### WR-01: Evidence still reports provider convergence without the ambiguous-invocation proof

**Files modified:** `scripts/verify_phase475.py`, `tests/test_phase475_evidence_verifier.py`, `docs/security/phase-475-evidence-results.json`, `docs/security/phase-475-evidence.md`
**Commits:** `6491370`, `c30dfc9`
**Applied fix:** Added the crash-after-provider-before-receipt selector to both D-01 and CR-01 and required it in the registry-closure test. Captured all governed gates from clean candidate `d63af86a9543fd678017d4c8a6ce1f641208ed35` in one default restricted-sandbox run, then published the generated evidence as its direct-child commit changing exactly the two evidence paths.
**Verification:** Independent `verify-capture` and `verify-publication` passed. The formal manifest records 2,619/2,619 passing nodes with zero non-pass outcomes, including both direct/subprocess network denial and process-group termination. The evidence verifier passed 47 tests. The publication records exact mypy coverage of 22 runtime files with zero diagnostics. Live AWS/DynamoDB, provider effects, deployment, and production smoke remain explicitly `NOT RUN`.

### WR-04: Pagination still stops before business eligibility filtering

**Files modified:** `src/stoa/services/teacher_dispatch_service.py`, `tests/test_teacher_dispatch.py`, `tests/test_teacher_availability.py`
**Commits:** `a5746b8`, `d63af86`
**Applied fix:** `_scan_filtered_items()` now accepts a final business-eligibility callback and continues across `LastEvaluatedKey` pages until that callback has accepted `limit` rows or the scan is exhausted. Teacher profiles are accepted only after role, active lifecycle, positive version, and active fence enrichment; questions are accepted only after their dispatch markers/status qualify. The availability fixture was aligned with those durable eligibility requirements when the full formal gate exposed its stale unfenced profile.
**Verification:** Non-empty rejected-first-page tests prove the second eligible profile/question page is read. Teacher availability and dispatch suites passed 23 tests; the final formal suite passed all 2,619 nodes.

### WR-05: Dispatch conditions regress the phase's exact mypy gate

**Files modified:** `src/stoa/db/repositories/question_repo.py`
**Commit:** `c81fd93`
**Applied fix:** Typed `additional_conditions` as the repository's concrete `QuestionItem` transaction-operation type and declared the assembled operations as `list[QuestionItem]`.
**Verification:** The exact ordered Phase 475 inventory completed with 22 source files, zero diagnostics, and exit code 0. Related behavior tests and Ruff also passed.

## Skipped Issues

None.

## Final Verification

- Governed clean candidate: `d63af86a9543fd678017d4c8a6ce1f641208ed35`.
- Immutable evidence publication: `c30dfc9d9ffead55199525f37ac59f50a9449481`.
- Default-sandbox formal extension: 2,619 passed; 0 failed, error, skipped, xfail, or xpass.
- Direct/subprocess network-denial node: passed in the default restricted sandbox.
- Process-group termination node: passed in the same formal manifest.
- Exact mypy gate: 22 files, 0 diagnostics.
- Evidence verifier: 47 passed.
- External AWS/DynamoDB, live provider, deployment, and production operations: `NOT RUN`.

---

_Fixed: 2026-07-23T11:30:27Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 2_
