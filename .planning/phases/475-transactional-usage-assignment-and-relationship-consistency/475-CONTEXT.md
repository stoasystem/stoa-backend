# Phase 475: Transactional Usage Assignment And Relationship Consistency - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 475 makes question submission, usage accounting, teacher takeover, parent/student relationships, rate limits, mistake answers, notification delivery admission, and completed account deletion converge under retry, concurrency, timeout, and partial failure.

It closes V9DATA-01 through V9DATA-08 and the Phase 473 runtime follow-ups `profile-version-cas`, `delivery-begin-dependency-classification`, and `completed-deletion-replay`. It does not add new learning features, billing flows, Web routes, or native/mobile work. STOA remains Web-first, and Phase 475 supplies trustworthy backend behavior for later real Web journeys.

</domain>

<decisions>
## Implementation Decisions

### Question Submission And Recovery
- **D-01:** An ambiguous question submission enters a visible recoverable `processing` state. The student may leave the page while the backend continues convergence; success turns that record into the original formal question, and a proven terminal failure restores the question allowance and gives an actionable resubmit result.
- **D-02:** The same logical submission and idempotency identity must never create another question, consume another question allowance, emit another usage-ledger event, or require the student to upload the same attachment again.
- **D-03:** A proven terminal creation failure restores the question allowance and records the usage-ledger operation as reversed. Any attachment whose upload already completed remains in the student's attachment library, continues to count toward storage quota, and can be reused later through its opaque attachment identity.
- **D-04:** One submission identity is bound to the exact original question text and ordered attachments. Reusing it with changed content is rejected with a structured mismatch outcome and friendly instruction to submit the edited content as a new request with a new identity; the original result is never overwritten.

### Concurrent Teacher Takeover
- **D-05:** The first teacher whose atomic backend claim succeeds is the unique winner. Every other concurrent claimant receives a deterministic conflict result; the Web UI says the question was taken by another teacher and refreshes its state.
- **D-06:** A losing claim creates no teacher session, notification, ownership change, or other durable side effect. The winning claim may produce exactly one session and exactly one takeover notification.
- **D-07:** Once ownership is durably assigned, a later temporary failure while creating the session or notification does not reopen the competition or revoke the winner. Recovery and same-winner retry converge the missing effects without duplication and return the original takeover result.
- **D-08:** An ordinary losing teacher sees only that another teacher has taken the question, not that teacher's identity. An authorized administrator may inspect the actual owner and audit trail.

### Parent/Student Relationships And Profile Concurrency
- **D-09:** Parent access requires the strict active bidirectional relationship established in Phase 472. If either direction is missing or disagrees, access is denied until the relationship is repaired and both directions agree.
- **D-10:** When forward and reverse rows identify different parents, reconciliation must not choose a winner or overwrite either side automatically. It reports the conflict and retains denied authorization until an administrator confirms the correct relationship.
- **D-11:** Reconciliation defaults to preview-only inspection. It reports normal, repairable, conflicting, and skipped relationships before mutation; apply requires administrator confirmation, rechecks record versions, skips and reports records changed since preview, and is idempotent across repeated runs.
- **D-12:** Concurrent profile operations modify only the fields they own and preserve the latest unrelated values, including locale and preferences. A privacy scrub clears only its sensitive fields; if a scrub and ordinary update target the same sensitive field, the privacy scrub wins and stale data cannot be restored.

### Rate Limits, Mistake Answers, Delivery, And Deletion Replay
- **D-13:** Each admitted logical chat or hint request consumes one rate-limit count. A request rejected because the limit is already reached does not increment the counter, and retrying the same admitted logical request after a network or provider failure does not consume another count.
- **D-14:** New incorrect practice attempts persist and return the student's bounded, display-safe submitted answer. Historical rows without a submitted answer are represented explicitly as “当时提交的答案未保存”; the system does not guess, substitute the correct answer, or present an empty value as known.
- **D-15:** Notification delivery becomes permanently `canceled_account_deletion` only when account deletion is positively established. A database, provider, or other dependency timeout/failure remains recoverable; a healthy retry may reserve and complete delivery exactly once.
- **D-16:** Replaying the identical account-deletion request after deletion already completed returns the original stored terminal `deleted` receipt. It does not reopen the command, rerun cleanup, return an account-not-found result, or manufacture a replay conflict.

### the agent's Discretion
- Choose internal transaction boundaries, command/operation row schemas, version-token representation, reconciliation scheduling, lease/backoff values, and exact structured error-code names while preserving all locked external behavior.
- Choose the exact friendly Web copy and processing-state polling/refresh mechanics, provided the copy remains simple and actionable and does not expose hidden resource or provider details.
- Choose safe bounds and normalization for submitted practice answers while preserving accurate round trips for accepted values and an explicit legacy-unknown state.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone And Phase Contract
- `.planning/ROADMAP.md` — Phase 475 goal, dependencies, likely slices, success criteria, evidence requirements, follow-up defects, and exit gate.
- `.planning/REQUIREMENTS.md` — Authoritative V9DATA-01 through V9DATA-08 contracts and Phase 473 follow-up mapping.
- `.planning/PROJECT.md` — v9.0 Web-first product boundary and milestone constraints.

### Inherited Authorization, Privacy, And Release Contracts
- `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-CONTEXT.md` — Strict bidirectional parent authorization, canonical single-role identity, teacher terminology, concealed resources, and structured safe errors inherited by this phase.
- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-CONTEXT.md` — Upload-intent consumption, durable attachment reuse, storage quota, practice-answer reveal, and privacy behavior that question convergence must preserve.
- `.planning/phases/474-deterministic-verification-and-gated-delivery/474-CONTEXT.md` — Deterministic failure-injection, repeated verification, and Web-first delivery constraints used to prove Phase 475.

### Audit And Follow-up Evidence
- `docs/audit/full-project-audit.md` — DATA-001, DATA-003, BUG-002, BUG-004, and BUG-006 failure descriptions and remediation expectations.
- `docs/audit/findings.json` — Machine-readable finding ownership, severity, affected code, and required evidence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/usage_ledger_service.py` and `src/stoa/db/repositories/usage_ledger_repo.py` already provide deterministic usage identities and question-usage reconciliation primitives to extend.
- `src/stoa/routers/teachers.py` and the existing notification service provide the current takeover and notification integration points.
- `src/stoa/db/repositories/user_repo.py` already owns forward/reverse parent binding reads and writes and is the natural boundary for conditional repair and shared profile-write discipline.
- `src/stoa/db/repositories/practice_repo.py` and `src/stoa/services/practice_projection_service.py` already recognize submitted-answer fields and can support safe legacy-unknown projection.
- `src/stoa/db/repositories/notification_repo.py`, `src/stoa/services/notification_service.py`, `src/stoa/db/repositories/account_deletion_repo.py`, and `src/stoa/services/account_deletion_service.py` already contain delivery and deletion command state machines that should be extended rather than replaced.

### Established Patterns
- Phase 472 authorization treats only a fresh, strict, active bidirectional parent/student relationship as authority; reconciliation cannot temporarily broaden that rule.
- Phase 473 uses stable idempotency identities, conditional/transactional commands, fenced effects, and redacted structured outcomes. Phase 475 should reuse those conventions for convergence and replay.
- API responses expose stable structured codes and safe actions, while the Web interface presents short, friendly, actionable messages.
- Formal evidence must include deterministic failure injection and concurrency barriers and must run through Phase 474's authoritative gate.

### Integration Points
- `src/stoa/routers/questions.py` joins question quota, usage ledger, upload consumption/association, and initial persistence; current partial-failure tests identify the convergence boundary.
- `src/stoa/routers/teachers.py` must join claim, session, and notification identities so concurrent takeover has one winner and recoverable downstream effects.
- Parent binding administration and repair connect through the existing user repository and admin repair route while normal profile writers and privacy scrubs share one non-overwriting concurrency discipline.
- `src/stoa/services/rate_limit.py` owns chat/hint admission counters and must distinguish a rejected attempt from an admitted logical request and its retries.
- Notification delivery begin and account-deletion endpoint projection must preserve typed dependency/business outcomes and stored terminal replay respectively.

</code_context>

<specifics>
## Specific Ideas

- Student-facing recovery should look like a durable “提交处理中” item rather than a false failure that may later silently appear in history.
- A proven terminal question failure returns the question allowance but does not delete a successfully uploaded reusable attachment; question allowance and attachment storage quota remain separate concepts.
- Relationship repair uses the user-facing concept “先预览，不修改” rather than exposing the term `dry-run` without explanation.
- Teacher takeover recovery is explained as preserving teacher A's confirmed ownership while automatically filling in a missing chat session or notification exactly once.

</specifics>

<deferred>
## Deferred Ideas

- Phase 476 owns checkout, provider billing, entitlement, and paid-access recovery; Phase 475 establishes compatible transaction/idempotency conventions but does not implement billing.
- Phases 477 and 478 own the actual Web adapters, processing-state presentation, and complete role journeys against these contracts.
- Native Expo/iOS/Android work remains deferred until the Web App has launched for testing and is stable.

</deferred>

---

*Phase: 475-Transactional Usage Assignment And Relationship Consistency*
*Context gathered: 2026-07-21*
