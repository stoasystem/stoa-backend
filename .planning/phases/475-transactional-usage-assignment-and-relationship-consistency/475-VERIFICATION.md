---
phase: 475-transactional-usage-assignment-and-relationship-consistency
verified: 2026-07-23T11:54:24Z
verified_head: 37f4ac0baac44633e938c356bde7c556c3d4bcb1
verified_candidate: d63af86a9543fd678017d4c8a6ce1f641208ed35
status: passed
score: 15/15 must-haves verified
requirements_score: 8/8 requirements satisfied
overrides_applied: 0
re_verification:
  previous_result: "8/15 with six grouped gaps"
  previous_score: 8/15
  gaps_closed:
    - "Durable question effects, strict replay, production terminal proof, exact compensation, and question state/version CAS"
    - "Active-teacher lifecycle/profile fencing in the atomic takeover claim"
    - "Dual parent/student fencing, status-aware relationship idempotency, and non-revivable revoked relationships"
    - "Immutable per-operation rate-limit replay receipts"
    - "Closed cross-account deletion discovery and conditional cleanup"
    - "Fail-closed unfiltered mypy, exhaustive source snapshots, and lower-boundary evidence"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "Live AWS DynamoDB behavior"
    addressed_in: "Phase 479"
    evidence: "Published Phase 475 evidence records LIVE-AWS-DYNAMODB as exact NOT RUN with owner_phase 479."
  - truth: "Live provider-effect behavior"
    addressed_in: "Phase 480"
    evidence: "Published Phase 475 evidence records LIVE-PROVIDER-EFFECTS as exact NOT RUN with owner_phase 480."
  - truth: "Deployment and production smoke"
    addressed_in: "Phase 480"
    evidence: "Published Phase 475 evidence records DEPLOYMENT-AND-PRODUCTION-SMOKE as exact NOT RUN with owner_phase 480."
---

# Phase 475: Transactional Usage, Assignment, and Relationship Consistency Verification

**Phase Goal:** Make the core learning and relationship writes converge under partial failure, retry, and concurrency.
**Verified:** 2026-07-23T11:54:24Z
**Status:** passed
**Re-verification:** Yes — after closure of the prior 8/15 verification and the final review-fix cycle

## Verdict

Phase 475 achieves its local codebase goal. The six grouped gaps from the prior
verification are closed in the actual repository implementation, not merely in
the summaries. All 15 observable truths and all 8 V9DATA requirements are
supported by substantive, wired code and lower-boundary tests.

The final governed candidate is
`d63af86a9543fd678017d4c8a6ce1f641208ed35`. The immutable publication commit
`c30dfc9d9ffead55199525f37ac59f50a9449481` is its direct child and changes only
the two Phase 475 evidence files. Current HEAD contains no committed
`src/`, `tests/`, or `scripts/` difference from that candidate, and the evidence
blob IDs still match the publication.

Live AWS/DynamoDB, live provider effects, deployment, and production smoke were
not run. They are explicit Phase 479/480 obligations and are neither counted as
Phase 475 passes nor treated as Phase 475 local-goal gaps.

## Goal Achievement

### Observable Truths

The ROADMAP success criteria, prior verification truths, CONTEXT decisions
D-01..D-16, and PLAN frontmatter were merged without reducing scope.

| # | Truth | Status | Code and behavioral evidence |
|---:|---|---|---|
| 1 | Question admission atomically binds the caller command, question quota, ledger, initial question, and attachment associations; same command/payload admits once. | ✓ VERIFIED | `question_submission_repo.py:2683` assembles the bounded DynamoDB transaction with command, counter, ledger, question, attachment, and account-fence conditions. Admission concurrency, commit-timeout, privacy, and mismatch nodes are in the 69-test question gate. |
| 2 | Receipted OCR/AI success survives local completion failure, and replay is strict for schema, command, digest, owner, generation, fence, question identity, state, and version. | ✓ VERIFIED | `begin_question_effect()` at line 677, `record_question_effect_result()` at 1468, and `complete_question_effect()` at 1615 form the durable effect/completion state machine. `classify_question_submission_replay()` at 490 performs the closed validation and strongly validates the loaded question. `questions.py:740` uses that classifier on preflight and replay paths. |
| 3 | A production-reachable proven terminal question failure reverses allowance/ledger exactly once, without treating retryable dependency failure as terminal. | ✓ VERIFIED | Expired exact invocation ownership is conditionally terminalized at `question_submission_repo.py:908`; `prove_terminal_question_failure()` at 1192 accepts only the closed proof set. `questions.py:355` promotes the proof and invokes explicit reconciliation. The crash-after-provider-before-receipt node proves at-most-once provider invocation, terminal convergence, exact-once reversal, stable replay, and fresh-key resubmission. |
| 4 | Terminal question compensation retains completed attachments and does not refund storage quota. | ✓ VERIFIED | The reversal transaction deliberately excludes attachment, association, object, and storage-quota rows. The lower-boundary terminal reversal test snapshots those rows across transition, compensation, response loss, and replay. |
| 5 | Concurrent teacher takeover produces one still-active winner, one owner/session, deterministic 409 loser, and no loser side effects. | ✓ VERIFIED | `question_repo.py:341` conditions the student fence, teacher fence, canonical active teacher PROFILE role/status/version, and expected question state/version in the same claim transaction. `teachers.py:340` passes the observed teacher lifecycle/version authority. Barrier tests cover two claimants, teacher deactivation/deletion, and AI/takeover interleaving. |
| 6 | The winning takeover has one deterministic notification effect that can recover without reopening ownership competition. | ✓ VERIFIED | The winner-only path calls `ensure_teacher_takeover_notification()` at `teachers.py:384`. Stable effect identity, lost-response recovery, and loser-zero-effect behavior are covered by the takeover/effect gates. |
| 7 | Parent/student forward and reverse bindings plus profile projection commit in one transaction, fenced by both accounts and both canonical profile versions; ordinary replay cannot revive revoked/inactive relationships. | ✓ VERIFIED | `user_repo.py:434` builds both account-fence/profile conditions, two status-aware relationship rows, and the narrow child profile CAS. `put_parent_student_relationship()` at 562 rejects non-active or conflicting replays. Authorized status changes use expected status/version and both lifecycle/profile fences. |
| 8 | Historical relationship repair is dry-run capable, version-bound, conflict-preserving, idempotent, and fails closed if either account/profile changes. | ✓ VERIFIED | `preview_parent_binding_repair()` at line 944 and `apply_parent_binding_repair()` at 983 validate preview identity/version, refuse conflicts, and reuse the atomic binding primitive. Repeated apply is zero-write; lifecycle/profile races fail conditionally. |
| 9 | Shared parent-profile writers and privacy scrub obey one version/CAS contract while preserving unrelated locale/preference bytes. | ✓ VERIFIED | `update_profile_fields_versioned()` at `user_repo.py:365` performs a strong read and narrow expected-version update. Account-deletion scrub uses narrow, conditional owned-field changes. Real writer-versus-scrub barriers pass in both orders. |
| 10 | Chat/hint rate admission increments at most once, rejected operations do not increment, and replay returns the original immutable receipt. | ✓ VERIFIED | `rate_limit.py:206` classifies an operation from stored `counter_value_after`, `limit`, and `receipt_expires_at`; admission writes that receipt beside the expected-value counter CAS in one transaction. A→B→replay-A tests preserve A's original receipt and 429 tests preserve the cap. |
| 11 | A wrong practice answer round-trips within bounds; historical missing answers are explicit unknowns and never substituted with the correct answer. | ✓ VERIFIED | `practice_projection_service.py:43` enforces bounded string/flat-list normalization; projection at line 72 distinguishes recorded from legacy unknown. `practice_repo.py:564` persists both schema fields before projection. Nine focused nodes pass. |
| 12 | Delivery begin distinguishes claim loss, proven account deletion, and transient dependency failure; only positively proven deletion terminalizes. | ✓ VERIFIED | `notification_repo.py:308-310` defines the closed dispositions. Failure classification at lines 498-556 uses ordered cancellation evidence plus strong deletion-fence proof; malformed/transient dependencies remain retryable. Service wiring performs one healthy retry and one completion. |
| 13 | An identical completed account-deletion request returns the stored terminal receipt through the endpoint and schedules no new cleanup. | ✓ VERIFIED | `terminal_deletion_receipt()` at `account_deletion_service.py:75` validates the nested stored receipt; `begin_or_replay_deletion()` at 342 returns it. `deps.py:169` has identity-hash discovery after active binding removal, and the auth route schedules work only for nonterminal receipts. |
| 14 | Phase evidence exercises the real persistence boundaries and fails closed for tool error, ambiguous mypy output, source-inventory drift, missing blobs, node drift, or non-pass outcomes. | ✓ VERIFIED | `scripts/verify_phase475.py` requires mypy exit 0, zero diagnostics, and an exact 22-source completion. `_source_snapshot()` at 1089 materializes every A/M/D/R/C path and validates exact status/cardinality. The evidence verifier's 47 adversarial tests pass. |
| 15 | Evidence binds a clean candidate and immutable two-file publication, has complete D/V9DATA/CR/WR coverage, contains no denylisted private data, and labels later live work honestly. | ✓ VERIFIED | Candidate/publication ancestry and exact changed paths were independently checked. JSON records 16 decisions, 8 requirements, 10 original review findings, 4 original warnings, 156 source-snapshot entries, 0 raw/published privacy matches, and three exact `NOT RUN` rows. Current HEAD evidence blobs equal the publication blobs. |

**Score:** 15/15 truths verified

### ROADMAP Success Criteria

| # | Roadmap criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Identical question retries converge to one question/admission accounting result after each tested timeout/failure point. | ✓ VERIFIED | The real repository failure matrix covers pre-commit failure, timeout-after-commit, receipted provider success followed by completion failure, conditional loss, and expired unreceipted invocation. Outcomes converge through stored success or proven terminal compensation without duplicate provider invocation. |
| 2 | Two concurrent takeovers produce one owner, session, notification, and deterministic 409 loser. | ✓ VERIFIED | Atomic question/session transaction, both account fences, teacher profile authority, deterministic notification effect, and barrier tests all pass. |
| 3 | Parent bindings cannot become one-sided; repair is dry-run/idempotent; profile writer/scrub races preserve unrelated bytes. | ✓ VERIFIED | Dual-fenced binding transaction, version-bound repair, status-aware non-revival, and both writer/scrub orderings pass. |
| 4 | 429 does not increase counters; delivery dependency failure stays recoverable and healthy retry completes once without false deletion. | ✓ VERIFIED | Immutable operation receipts/counter CAS and the four-outcome delivery state machine are wired and covered. |
| 5 | Mistake answers/legacy unknown and completed-deletion terminal replay behave safely. | ✓ VERIFIED | Bounded answer storage/projection and real endpoint terminal replay with zero new cleanup both pass. |

## Requirements Coverage

| Requirement | Source plans | Status | Implementation evidence |
|---|---|---|---|
| V9DATA-01 | 475-01..03, 14..20, 35, 36, 39, 42..45 | ✓ SATISFIED | Atomic admission, required opaque idempotency, durable effects, strict replay, expected-state/version question mutation, proven terminal compensation, and fail-closed evidence. |
| V9DATA-02 | 475-04, 05, 17, 21, 27, 34, 39, 44, 45 | ✓ SATISFIED | One transactional owner/session winner, teacher lifecycle/profile fence, winner-only deterministic effect, and question-writer CAS. |
| V9DATA-03 | 475-06, 07, 22, 23, 25, 26, 30, 32, 44, 45 | ✓ SATISFIED | Bidirectional atomic rows, dual account/profile fences, status-aware replay, privileged transition, version-bound repair, and relationship deletion cleanup. |
| V9DATA-04 | 475-09, 24, 44, 45 | ✓ SATISFIED | Expected-counter transaction plus immutable operation-owned receipt; rejection and replay are zero-increment. |
| V9DATA-05 | 475-10, 31, 37, 40, 44, 45 | ✓ SATISFIED | Bounded display-safe answer persistence and explicit legacy unknown projection. |
| V9DATA-06 | 475-08, 30, 32, 44, 45 | ✓ SATISFIED | Narrow version/CAS writers and deletion scrub preserving unrelated fields. |
| V9DATA-07 | 475-11, 25, 28, 34, 44, 45 | ✓ SATISFIED | Typed delivery dispositions, strong deletion proof, retryable dependency path, and notification identity cleanup. |
| V9DATA-08 | 475-12, 29, 33, 41, 44, 45 | ✓ SATISFIED | Strict stored terminal receipt, post-deletion command discovery, and no terminal rescheduling. |

No Phase 475 requirement is orphaned. V9DATA-01..08 occur in the 45 PLAN
frontmatters and all have implementation/evidence coverage.

## Atomic Plan Delivery

| Check | Result | Status |
|---|---:|---|
| Numbered PLAN files | 45 | ✓ |
| Numbered SUMMARY files | 45 | ✓ |
| `<task type="auto">` rows | 45 — exactly one per PLAN | ✓ |
| Requirements represented across PLANs | V9DATA-01..08 | ✓ |
| SUMMARY commit references resolved | 74/74 | ✓ |
| Final code review | 60 files, 0 critical, 0 warning, 0 info | ✓ |

Plans 475-14..45 close the prior verification gaps in dependency order: caller
idempotency/privacy, question CAS/effects/replay/terminal compensation, takeover
and relationship fences, immutable rate receipts, deletion discovery/cleanup,
exact-file typing, fail-closed evidence, complete coverage, and immutable
publication. Every plan remains atomic at one implementation task.

The ROADMAP's individual plan checkbox rows are stale for some completed plans,
but its Phase 475 header says 45/45 and the actual 45 PLAN/SUMMARY pairs,
single-task cardinality, commit references, candidate tree, and tests establish
delivery. This metadata inconsistency does not affect goal behavior.

## Required Artifacts

| Artifact | Expected | Exists/Substantive | Wiring/Data | Status |
|---|---|---|---|---|
| `src/stoa/db/repositories/question_submission_repo.py` | Atomic admission and closed effect/replay/terminal state machine | 2,800+ lines; real transaction builders | Used by question route and reconciliation; strong reads and exact conditional writes | ✓ VERIFIED |
| `src/stoa/routers/questions.py` | Required-key request path and convergence orchestration | Substantive route/service logic | Strict replay, effect receipt, completion, terminal proof, and explicit reconciliation all connected | ✓ VERIFIED |
| `src/stoa/db/repositories/question_repo.py` | Versioned question mutation and atomic takeover | Substantive conditional repository | Used by question, teacher, and dispatch writers; all governed writers pass expected state/version | ✓ VERIFIED |
| `src/stoa/db/repositories/user_repo.py` | Dual-fenced relationship/profile transaction and repair | Substantive transaction/repair logic | Parent/student routes and admin preview/apply use the same status-aware primitive | ✓ VERIFIED |
| `src/stoa/services/rate_limit.py` | Capped idempotent counter with stable receipt | Substantive operation/counter transaction | Hint route passes caller operation identity; replay reads operation-owned receipt | ✓ VERIFIED |
| Practice service/repository/router | Bounded answer write and real mistake projection | Substantive validation/persistence | Request → normalize → persist → projection uses real stored data | ✓ VERIFIED |
| Notification repository/service | Typed delivery begin and recoverable execution | Substantive disposition/effect logic | Repository proof maps explicitly to service retry/cancel/reserve branches | ✓ VERIFIED |
| Account deletion repository/service/dependency/route | Cross-account discovery, conditional cleanup, terminal replay | Substantive closed registries and branch writers | Discovery → two clean epochs → final stored receipt → endpoint replay is complete | ✓ VERIFIED |
| `scripts/verify_phase475.py` | Fail-closed capture and publication verification | Substantive 1,300+ line verifier | Exact gate registry, source snapshot, privacy, mypy, and Git publication checks connected | ✓ VERIFIED |
| Phase 475 test/evidence surfaces | Lower-boundary proof rather than stubs | 34 reviewed test files plus generated evidence | 657 reviewed tests and 2,619 formal tests pass | ✓ VERIFIED |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Question route | Admission transaction | `admit_question_submission()` | ✓ WIRED | One bounded transaction creates all initial durable state. |
| Provider boundary | Durable effect/result | begin → invoke → result receipt | ✓ WIRED | Result receipt precedes completion; expired unreceipted invocation cannot be reclaimed for a duplicate call. |
| Effect result | Question + command completion | `complete_question_effect()` | ✓ WIRED | Exact command/question/effect versions and allowed states are conditioned together. |
| Replay | Command/question authority | `classify_question_submission_replay()` | ✓ WIRED | No shortcut bypass remains. |
| Every governed question writer | Takeover state/version | `mutate_question()` registry | ✓ WIRED | AI, escalation, feedback, reply, resolve, and dispatch interleavings are conditional. |
| Takeover route | Teacher/student lifecycle | account fences + teacher PROFILE condition | ✓ WIRED | Authority observation participates in the claim transaction. |
| Takeover winner | Notification effect | deterministic effect identity | ✓ WIRED | Loser cannot enter the effect branch. |
| Parent binding/repair | Both account and profile versions | shared atomic relationship primitive | ✓ WIRED | Apply cannot revive inactive rows or cross a lifecycle change. |
| Rate operation | Immutable replay result | stored receipt fields | ✓ WIRED | Replaying A after B returns A's original counter/limit/expiry. |
| Delivery intent | Typed service routing | `DeliveryBeginDisposition` | ✓ WIRED | Only strong proven deletion cancels; dependency failure retries. |
| Deletion discovery | Cross-account cleanup branches | closed entity/field registry | ✓ WIRED | Parent, teacher, actor, and reviewed metadata identities are included. |
| Deletion endpoint | Stored terminal receipt | dependency identity fallback + terminal scheduling gate | ✓ WIRED | Completed replay is effect-free. |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces real/stable data | Status |
|---|---|---|---|---|
| Question replay | Original processing/final/terminal result | Strong command, effect, and question reads | Exact receipt or exact proven terminal state; no static fallback | ✓ FLOWING |
| Terminal compensation | Counter/ledger reversal | Persisted command/effect/question proof | One conditional reversal identity; attachments excluded | ✓ FLOWING |
| Takeover result | Owner/session/notification | Atomic question claim and deterministic IDs | One winner, one durable session/effect | ✓ FLOWING |
| Relationship projection | Forward/reverse/profile rows | One dual-fenced transaction | Real rows with exact active status/version | ✓ FLOWING |
| Rate replay receipt | Counter value/limit/expiry | Immutable operation row | Stable after other operations | ✓ FLOWING |
| Mistake review | `yourAnswer` / `answerState` | Stored attempt fields | Bounded real answer or explicit legacy unknown | ✓ FLOWING |
| Delivery disposition | Claim/fence/dependency evidence | DynamoDB cancellation reasons plus strong reads | Closed, typed, non-static decision | ✓ FLOWING |
| Deletion replay | `deleted` terminal receipt | Stored nested command receipt | Byte-stable and zero-reschedule | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command / environment | Result | Status |
|---|---|---|---|
| Final reviewed Phase 475 and inherited regression scope | 34 test files listed in final `475-REVIEW.md`, current workspace | 657 passed, 2 warnings | ✓ PASS |
| Evidence verifier adversarial coverage | `pytest -q tests/test_phase475_evidence_verifier.py` | 47 passed | ✓ PASS |
| Exact runtime type gate | Mypy over the evidence JSON's ordered 22-file runtime inventory | 22 source files, 0 diagnostics, exit 0 | ✓ PASS |
| Governed lint gate | Ruff over 22 runtime files, verifier, and verifier test | All checks passed | ✓ PASS |
| Formal release extension | Exact candidate in isolated clean backend checkout with canonical frontend/infra siblings | 2,619 passed, 2 warnings, 0 non-pass outcomes | ✓ PASS |
| Immutable publication | `verify-publication` in isolated clean checkout | Exit 0 | ✓ PASS |
| Candidate/publication topology | Git ancestry, changed paths, blob IDs | Direct child; exactly two evidence paths; HEAD blobs identical | ✓ PASS |
| Post-candidate committed runtime drift | `git diff --name-only candidate HEAD -- src tests scripts` | 0 paths | ✓ PASS |
| Patch hygiene | `git diff --check` | Exit 0 | ✓ PASS |

The independently repeated formal suite matches the checked evidence's
2,619/2,619 receipt. The checked JSON additionally records focused gate counts:
question 69, takeover 19, relationship 70, rate 11, mistake 9, delivery 25,
deletion 64, and inherited auth/privacy 329; all exit 0.

### Probe Execution

No PLAN or SUMMARY declares a `probe-*.sh`, and there is no conventional Phase
475 shell probe. The phase-specific executable verifier is
`scripts/verify_phase475.py`; its publication mode was run independently and
passed.

## Prior Gap and Review Closure

| Prior concern | Closure evidence | Status |
|---|---|---|
| CR-01 provider success/local persistence gap | Durable intent/result receipt and conditional completion; the additional expired-invocation ambiguity is exact-owner/version terminalized and compensated without a second provider call | ✓ CLOSED |
| CR-02 replay integrity | One strict classifier validates all command/question authority and every route replay branch uses it | ✓ CLOSED |
| CR-03 question CAS | Governed writers use expected state/version and increment version | ✓ CLOSED |
| CR-04 teacher fence | Active teacher account fence and canonical PROFILE role/status/version are in the claim transaction | ✓ CLOSED |
| CR-05 parent fence | Both parent and student fences/profile versions participate in binding and status transitions | ✓ CLOSED |
| CR-06 revoked revival | Ordinary replay requires identical active status; only the privileged transition can change status/version | ✓ CLOSED |
| CR-07 terminal producer | Closed production producer plus explicit exact-once reconciliation is reachable from the route/service state machine | ✓ CLOSED |
| CR-08 raw idempotency | Caller key is required and represented durably only through opaque digest/coordinates | ✓ CLOSED |
| CR-09 rate receipt | Operation row owns immutable counter/limit/expiry receipt | ✓ CLOSED |
| CR-10 deletion discovery | Closed entity/field registry and dedicated relationship/teacher/notification cleanup branches cover cross-account references | ✓ CLOSED |
| Original WR-01..04 evidence/tooling warnings | Required key, fail-closed mypy, exhaustive source snapshots, and real lower-boundary persistence tests are in the exact registry | ✓ CLOSED |
| Final review-fix CR-01 / WR-01 / WR-04 / WR-05 | Expired invocation, evidence registry/publication, dispatch pagination eligibility, and exact mypy typing were fixed; iteration 3 reports zero findings | ✓ CLOSED |

## Anti-Patterns and Quality Notes

No unreferenced `TBD`, `FIXME`, or `XXX` marker exists in the governed Phase 475
runtime/verifier inventory. No empty implementation or hardcoded user-visible
data path was found. The phrase “placeholder login codes” in `auth.py` describes
an intentional fail-closed rejection for V9AUTH-06 and is not a stub.

An extra Ruff run over all 34 review test files, beyond the governed lint
inventory, reports one unused import in
`tests/test_phase473_notification_deletion.py:10`. The import predates Phase 475
and the test module executes successfully in both the 657-test and formal
suites. This is a non-runtime hygiene note, not a Phase 475 goal gap.

The working tree also contains unrelated user edits in `README.md`, two
provisioning/seed scripts, and new AWS operator-identity files. They were not
modified or used as candidate evidence. Candidate verification occurred in an
isolated clean checkout.

## Deferred External Obligations

| Obligation | Status | Owner | Phase 475 treatment |
|---|---|---|---|
| `LIVE-AWS-DYNAMODB` | NOT RUN | Phase 479 | Deferred exactly; not claimed as passed and not a local Phase 475 blocker |
| `LIVE-PROVIDER-EFFECTS` | NOT RUN | Phase 480 | Deferred exactly; not claimed as passed and not a local Phase 475 blocker |
| `DEPLOYMENT-AND-PRODUCTION-SMOKE` | NOT RUN | Phase 480 | Deferred exactly; not claimed as passed and not a local Phase 475 blocker |

## Human Verification Required

None for the Phase 475 local backend goal. Concurrency, failure recovery,
replay, redaction, and persistence behavior are programmatically covered.
External live-system work is explicitly deferred above rather than silently
converted into human verification.

## Gaps Summary

No actionable Phase 475 gap remains. The previous six grouped gaps are closed,
the final review has zero findings, all 45 atomic plans have corresponding
summaries and code/test evidence, all local gates pass, and the immutable
evidence publication is source-bound. Phase 475 is complete and may proceed to
later phases, with the three named external obligations retained for 479/480.

---

_Verified: 2026-07-23T11:54:24Z_
_Verifier: the agent (gsd-verifier)_
