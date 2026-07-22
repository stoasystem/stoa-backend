---
phase: 475
slug: transactional-usage-assignment-and-relationship-consistency
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-22
---

# Phase 475 — Validation Strategy

> Gap-closure validation contract for plans 475-14 through 475-45. This artifact is required because `475-RESEARCH.md` contains a Validation Architecture section; the gap revision supersedes the earlier note that no separate file was required.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest via `.venv/bin/python`, mypy, Ruff, and `scripts/verify_phase475.py` |
| **Config file** | `pyproject.toml`, `mypy.ini`, `scripts/verify_phase475.py` |
| **Quick run command** | `.venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py` |
| **Full suite command** | `.venv/bin/python -m pytest -q tests/test_phase475_*.py tests/test_phase473_account_deletion*.py tests/test_phase473_notification_deletion.py tests/test_phase473_delivery_intent_recovery.py` |
| **Estimated runtime** | ~30 seconds for the gap-focused local suite; immutable capture has its own candidate-bound gate |

---

## Sampling Rate

- **After every task commit:** Run the plan row's exact automated command below.
- **After every plan wave:** Run `.venv/bin/python -m pytest -q tests/test_phase475_*.py tests/test_phase473_account_deletion*.py tests/test_phase473_notification_deletion.py tests/test_phase473_delivery_intent_recovery.py`.
- **Before `$gsd-verify-work`:** Plan 475-45 `verify-publication` and the complete evidence-verifier suite must be green.
- **Max feedback latency:** 60 seconds for every per-task command; candidate capture is explicitly handled by Plan 475-45 after all commits.

## Dependency Gate

| Stage | Plans | Required predecessor |
|-------|-------|----------------------|
| Functional gap closure | 475-14..29 | Existing completed Plans 475-01..13 where referenced |
| Independent exact-file type cleanup | 475-30..41 | The functional plans that establish each touched file's final behavior |
| Fail-closed mypy verifier | 475-42 | Every functional and type-cleanup plan 475-14..41 |
| Exhaustive source snapshot | 475-43 | 475-42 |
| Truthful D/V9DATA/CR/WR coverage registry | 475-44 | 475-43 |
| Immutable evidence publication | 475-45 | 475-44 |

This chain is intentionally explicit: no verifier, snapshot, coverage, or publication plan can execute against a partial functional/type candidate.

---

## Multi-Source Coverage Audit

| Source | ID | Required outcome or constraint | Gap plans | Status |
|--------|----|--------------------------------|-----------|--------|
| GOAL | — | Core learning and relationship writes converge under partial failure, retry, and concurrency | 475-14..45 | COVERED |
| REQ | V9DATA-01 | Atomic/convergent question admission, effect recovery, replay, and exact compensation | 475-14..20, 475-35, 475-36, 475-39, 475-42..45 | COVERED |
| REQ | V9DATA-02 | One active teacher winner/session/notification with safe deletion cleanup | 475-17, 475-21, 475-27, 475-34, 475-37, 475-39, 475-42..45 | COVERED |
| REQ | V9DATA-03 | Dual-fenced non-revivable relationships, repair, and deletion scrub | 475-22, 475-23, 475-25, 475-26, 475-32, 475-38, 475-42..45 | COVERED |
| REQ | V9DATA-04 | Stable immutable rate-operation receipt | 475-24, 475-42..45 | COVERED |
| REQ | V9DATA-05 | Bounded exact submitted-answer/legacy-unknown behavior remains type-safe | 475-31, 475-40, 475-42..45 | COVERED |
| REQ | V9DATA-06 | Shared profile CAS and deletion orchestration remain type-safe | 475-30, 475-32, 475-33, 475-42..45 | COVERED |
| REQ | V9DATA-07 | Delivery/deletion identity handling remains recoverable and reference-clean | 475-25, 475-28, 475-30, 475-33, 475-34, 475-42..45 | COVERED |
| REQ | V9DATA-08 | Stored completed-deletion receipt replays without effects | 475-29, 475-30, 475-33, 475-41, 475-42..45 | COVERED |
| RESEARCH | durable commands | Use application-owned opaque durable identities, not transport-token lifetime | 475-14..16 | COVERED |
| RESEARCH | effect boundaries | Keep provider effects outside DynamoDB transactions but durably receipt and reconcile them | 475-17..20 | COVERED |
| RESEARCH | claim/binding/rate boundaries | Use the smallest state/version/lifecycle transaction or CAS boundary per command | 475-21..24 | COVERED |
| RESEARCH | deletion reference closure | Discover and entity-CAS-clean parent, teacher, and notification cross-account references | 475-25..28 | COVERED |
| RESEARCH | deterministic tests | Transaction-shape, strong-read, barrier, failure-injection, replay, and two-clean-epoch proof | 475-14..29 plus Wave 0 below | COVERED |
| RESEARCH | static assurance | Exact-file type cleanup precedes an unfiltered fail-closed mypy gate | 475-30..42 | COVERED |
| RESEARCH | immutable evidence | Exhaustive snapshot, observed-node coverage, redacted immutable publication | 475-43..45 | COVERED |
| RESEARCH | external boundary | Live AWS/provider/deployment work stays exact later-phase `NOT RUN` | 475-44, 475-45 | COVERED |
| CONTEXT | D-01 | Durable visible processing and convergence | 475-17, 475-18, 475-20, 475-44 | COVERED |
| CONTEXT | D-02 | Same logical submission never duplicates question/quota/ledger/upload | 475-14..19, 475-44 | COVERED |
| CONTEXT | D-03 | Proven terminal failure reverses allowance/ledger and retains attachment storage | 475-20, 475-44 | COVERED |
| CONTEXT | D-04 | Same identity binds exact content; changed content conflicts | 475-14, 475-15, 475-19, 475-44 | COVERED |
| CONTEXT | D-05 | Atomic first teacher wins | 475-17, 475-21, 475-44 | COVERED |
| CONTEXT | D-06 | Loser creates no session/notification/ownership side effect | 475-21, 475-44 | COVERED |
| CONTEXT | D-07 | Winner-owned follow-up effects recover without reopening competition | 475-17, 475-18, 475-44 | COVERED |
| CONTEXT | D-08 | Loser identity remains concealed | 475-37, 475-44 | COVERED |
| CONTEXT | D-09 | Parent access requires strict active bidirectional relationship | 475-22, 475-23, 475-26, 475-44 | COVERED |
| CONTEXT | D-10 | Conflict repair never chooses a parent | 475-22, 475-23, 475-26, 475-44 | COVERED |
| CONTEXT | D-11 | Preview-first version-bound idempotent reconciliation | 475-23, 475-38, 475-44 | COVERED |
| CONTEXT | D-12 | Field-owned profile writes preserve unrelated values and scrub wins | 475-30, 475-32, 475-33, 475-44 | COVERED |
| CONTEXT | D-13 | One admitted rate operation counts once and replays its receipt | 475-24, 475-44 | COVERED |
| CONTEXT | D-14 | Submitted mistake answer round-trips; historical absence is unknown | 475-31, 475-40, 475-44 | COVERED |
| CONTEXT | D-15 | Only proven deletion terminalizes notification delivery | 475-34, 475-44 | COVERED |
| CONTEXT | D-16 | Completed deletion replays stored terminal receipt without cleanup | 475-29, 475-41, 475-44 | COVERED |

Deferred billing, Web/native adapters, live AWS/provider effects, deployment, and production smoke are excluded exactly as assigned by CONTEXT/VERIFICATION; no gap plan implements them.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 475-14-01 | 14 | 1 | V9DATA-01 | T-475-14-01/02 | Missing/invalid caller identity is effect-free | route/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_replay.py -k 'idempotency or lost_response or missing'` | ✅ | ⬜ pending |
| 475-15-01 | 15 | 2 | V9DATA-01 | T-475-15-01/02 | Raw caller key never persists or appears in output | repo/route/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_admission.py tests/test_phase475_question_replay.py -k 'privacy or idempotency or replay or mismatch'` | ✅ | ⬜ pending |
| 475-16-01 | 16 | 3 | V9DATA-01 | T-475-16-01/02 | Reconciliation accepts/emits opaque digest only | job/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_reconciliation.py -k 'cli or lambda or privacy or preview or replay'` | ✅ | ⬜ pending |
| 475-17-01 | 17 | 3 | V9DATA-01/02 | T-475-17-01/02 | Every question writer is expected-state/version CAS | repo/concurrency/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_state_cas.py::test_ai_completion_cannot_overwrite_teacher_takeover` | ❌ W0 | ⬜ pending |
| 475-18-01 | 18 | 4 | V9DATA-01 | T-475-18-01/02/03 | Provider result is durable before conditional completion | persistence-boundary/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_effect_recovery.py::test_provider_result_receipt_recovers_after_local_completion_failure` | ❌ W0 | ⬜ pending |
| 475-19-01 | 19 | 5 | V9DATA-01 | T-475-19-01/02 | Replay validates authoritative command and loaded owner | repo/route/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_replay.py -k 'foreign or owner or schema or generation or mismatch'` | ✅ | ⬜ pending |
| 475-20-01 | 20 | 6 | V9DATA-01 | T-475-20-01/02/03 | Only proven terminal failure compensates exactly once | state-machine/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_question_effect_recovery.py tests/test_phase475_question_reconciliation.py tests/test_phase475_question_replay.py` | ❌ W0 dependency | ⬜ pending |
| 475-21-01 | 21 | 4 | V9DATA-02 | T-475-21-01/02 | Active canonical teacher is rechecked in claim transaction | transaction/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_teacher_takeover.py` | ✅ | ⬜ pending |
| 475-22-01 | 22 | 1 | V9DATA-03 | T-475-22-01/02 | Both account lifecycle/profile observations fence binding | transaction/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_parent_binding_transaction.py tests/test_phase475_parent_binding_reconciliation.py` | ✅ | ⬜ pending |
| 475-23-01 | 23 | 2 | V9DATA-03 | T-475-23-01/02 | Create/replay cannot revive non-active relationship | lifecycle/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_parent_binding_transaction.py tests/test_phase475_parent_binding_reconciliation.py -k 'status or revoked or inactive or replay or admin'` | ✅ | ⬜ pending |
| 475-24-01 | 24 | 1 | V9DATA-04 | T-475-24-01/02/03 | Replay returns immutable D-13 operation receipt | concurrency/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_rate_limit.py` | ✅ | ⬜ pending |
| 475-25-01 | 25 | 1 | V9DATA-02/03/07 | T-475-25-01/02 | Strong discovery sees every reviewed cross-account field | discovery/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_deletion_discovery.py::test_cross_account_identity_registry_and_two_clean_epochs` | ❌ W0 | ⬜ pending |
| 475-26-01 | 26 | 3 | V9DATA-03 | T-475-26-01/02 | Relationship identities CAS-clean and reach two clean epochs | branch/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_deletion_relationship_scrub.py::test_relationship_identity_scrub_retries_cas_then_requires_two_clean_epochs` | ❌ W0 | ⬜ pending |
| 475-27-01 | 27 | 5 | V9DATA-02 | T-475-27-01/02 | Teacher identity scrub preserves student question content | branch/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_deletion_teacher_identity_scrub.py::test_teacher_identity_scrub_preserves_student_question_and_requires_two_clean_epochs` | ❌ W0 | ⬜ pending |
| 475-28-01 | 28 | 2 | V9DATA-07 | T-475-28-01/02 | Notification reference scrub preserves recipient/effect receipt | branch/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_deletion_notification_identity_scrub.py::test_notification_identity_scrub_retries_cas_then_requires_two_clean_epochs` | ❌ W0 | ⬜ pending |
| 475-29-01 | 29 | 1 | V9DATA-08 | T-475-29-01/02 | D-16 terminal replay is byte-stable and effect-free | endpoint/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_completed_deletion_replay.py::test_completed_deletion_replays_stored_receipt_without_new_effects` | ✅ | ⬜ pending |
| 475-30-01 | 30 | 6 | V9DATA-02/03/06/07/08 | T-475-30-01 | Deletion repository has zero unfiltered diagnostics | static+regression | `.venv/bin/mypy src/stoa/db/repositories/account_deletion_repo.py` | ✅ | ⬜ pending |
| 475-31-01 | 31 | 1 | V9DATA-05 | T-475-31-01 | Practice repository typing preserves answer privacy | static+regression | `.venv/bin/mypy src/stoa/db/repositories/practice_repo.py` | ✅ | ⬜ pending |
| 475-32-01 | 32 | 4 | V9DATA-03/06 | T-475-32-01 | User repository typing preserves relationship denial | static+regression | `.venv/bin/mypy src/stoa/db/repositories/user_repo.py` | ✅ | ⬜ pending |
| 475-33-01 | 33 | 6 | V9DATA-02/03/06/07/08 | T-475-33-01 | Deletion service typing cannot fabricate completion | static+regression | `.venv/bin/mypy src/stoa/services/account_deletion_service.py` | ✅ | ⬜ pending |
| 475-34-01 | 34 | 3 | V9DATA-02/07 | T-475-34-01 | Notification typing preserves typed recovery/privacy | static+regression | `.venv/bin/mypy src/stoa/services/notification_service.py` | ✅ | ⬜ pending |
| 475-35-01 | 35 | 7 | V9DATA-01 | T-475-35-01/02 | Ledger typing preserves opaque exact accounting | static+regression | `.venv/bin/mypy src/stoa/services/usage_ledger_service.py` | ✅ | ⬜ pending |
| 475-36-01 | 36 | 7 | V9DATA-01 | T-475-36-01 | Subscription typing preserves allowance/refund values | static+regression | `.venv/bin/mypy src/stoa/services/subscription_service.py` | ✅ | ⬜ pending |
| 475-37-01 | 37 | 5 | V9DATA-02 | T-475-37-01/02 | Teacher typing preserves canonical role and D-08 privacy | static+regression | `.venv/bin/mypy src/stoa/routers/teachers.py` | ✅ | ⬜ pending |
| 475-38-01 | 38 | 3 | V9DATA-03 | T-475-38-01 | Admin typing preserves capability and version gates | static+regression | `.venv/bin/mypy src/stoa/routers/admin.py` | ✅ | ⬜ pending |
| 475-39-01 | 39 | 7 | V9DATA-01/02 | T-475-39-01/02 | Question typing preserves replay/effect/terminal safety | static+regression | `.venv/bin/mypy src/stoa/routers/questions.py` | ✅ | ⬜ pending |
| 475-40-01 | 40 | 1 | V9DATA-05 | T-475-40-01 | Practice typing preserves D-14 input/output boundary | static+regression | `.venv/bin/mypy src/stoa/routers/practice.py` | ✅ | ⬜ pending |
| 475-41-01 | 41 | 2 | V9DATA-08 | T-475-41-01 | Auth typing preserves D-16 zero-reschedule replay | static+regression | `.venv/bin/mypy src/stoa/routers/auth.py` | ✅ | ⬜ pending |
| 475-42-01 | 42 | 8 | V9DATA-01..08 | T-475-42-01/02/03 | Nonzero/ambiguous mypy can never pass | verifier/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py::test_mypy_gate_fails_closed_for_every_nonzero_or_ambiguous_outcome` | ✅ | ⬜ pending |
| 475-43-01 | 43 | 9 | V9DATA-01..08 | T-475-43-01/02 | Every Git path/status has explicit snapshot evidence | verifier/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py::test_source_snapshot_is_exhaustive_for_all_git_statuses` | ✅ | ⬜ pending |
| 475-44-01 | 44 | 10 | V9DATA-01..08 | T-475-44-01/02/03 | Truthful exact D/V9DATA/CR/WR registry only | verifier/TDD | `.venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py::test_coverage_registry_requires_all_truthful_gap_nodes` | ✅ | ⬜ pending |
| 475-45-01 | 45 | 11 | V9DATA-01..08 | T-475-45-01/02/03/04 | Immutable two-file publication over one clean candidate | evidence | `.venv/bin/python scripts/verify_phase475.py verify-publication && .venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase475_question_state_cas.py` — Plan 475-17 creates `test_ai_completion_cannot_overwrite_teacher_takeover` before changing question writers.
- [ ] `tests/test_phase475_question_effect_recovery.py` — Plan 475-18 creates `test_provider_result_receipt_recovers_after_local_completion_failure` before effect implementation; Plan 475-20 extends it for terminal proof.
- [ ] `tests/test_phase475_deletion_discovery.py` — Plan 475-25 creates the exact cross-account registry/pagination/two-clean-epoch node before discovery changes.
- [ ] `tests/test_phase475_deletion_relationship_scrub.py` — Plan 475-26 creates the formal forward/reverse/profile CAS-loss node before cleanup changes.
- [ ] `tests/test_phase475_deletion_teacher_identity_scrub.py` — Plan 475-27 creates the question/session content-preserving scrub node before cleanup changes.
- [ ] `tests/test_phase475_deletion_notification_identity_scrub.py` — Plan 475-28 creates the recipient/effect-preserving notification scrub node before repository changes.

The existing `.venv`, pytest configuration, mypy configuration, Ruff configuration, and verifier harness require no installation. Each missing file is owned by the named TDD plan's RED step; no placeholder or empty scaffold may satisfy Wave 0.

---

## Manual-Only Verifications

All Phase 475 gap behaviors have automated local verification. Live AWS DynamoDB, provider effects, deployment, and production smoke are not manual checks for this phase; they remain exact `NOT RUN` obligations owned by Phases 479/480.

---

## Validation Sign-Off

- [x] All 32 gap tasks have an exact automated command.
- [x] Sampling continuity has no three consecutive tasks without automated verification.
- [x] Wave 0 names every missing test file, owner plan, and first failing node.
- [x] No watch-mode flags are present.
- [x] Per-task feedback latency target is under 60 seconds.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** pending execution; `wave_0_complete` becomes true after plans 475-17, 475-18, and 475-25..28 create and run the listed RED tests.
