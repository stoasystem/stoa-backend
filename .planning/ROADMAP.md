# Roadmap: v5.11 Additional Usage Ledger Coverage

**Status:** Complete
**Created:** 2026-07-04
**Prior milestone:** v5.10 Account Operations Frontend And Production Readiness
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone requirements:** `.planning/milestones/v5.11-REQUIREMENTS.md`

## Goal

Extend usage ledger coverage beyond question submissions so paid-limit behavior and parent/admin support explanations can account for chat, hints, teacher-help, and practice/generation usage without exposing private learning content.

## Why This Is The Next Milestone

v5.6-v5.10 closed the account operations chain:

- v5.6 resolves effective entitlement and enforces student question quota from parent billing/manual override.
- v5.7 records privacy-safe question usage ledger events and reconciles them with counters.
- v5.8 enforces Cognito-backed email verification and gates unsupported login-code behavior.
- v5.9 exposes consolidated parent/admin account operations APIs.
- v5.10 makes those states usable in the web frontend and records production read-only smoke planning.

The remaining gap is that usage explanations still primarily mean question submissions. Parents and admins can see usage state, but chat, hint, teacher-help, and practice/generation actions are not yet governed by the same durable ledger taxonomy. v5.11 should add that coverage without changing paid plans, weakening privacy boundaries, or destabilizing the existing question counter path.

## Current Reality

Backend evidence:

- `src/stoa/services/usage_ledger_service.py` currently defines question submission ledger actions, question idempotency keys, daily counter reconciliation, and parent/admin usage summaries.
- `src/stoa/routers/questions.py` records question usage after successful counter increment.
- `src/stoa/services/account_operations_service.py` consumes usage summaries for parent/admin account operations.
- Teacher-help behavior exists through question escalation and teacher/tutor queue workflows.
- Practice, assignment, curriculum, and generation-related flows exist in practice, adaptive learning, assignment, and curriculum service/router areas.

Known constraints:

- The existing daily question counter remains the enforcement source for question quota.
- Not every usage action is necessarily quota-enforced; some actions are support-visible only.
- Ledger and summary payloads must not store raw prompts, answers, teacher replies, generated content, provider payloads, verification codes, tokens, or private artifact keys.
- If no explicit hint or chat endpoint exists for a desired product concept, v5.11 should document the action taxonomy and instrument only existing successful backend flows.

## Implementation Strategy

- Start with a governed action taxonomy before adding new writes.
- Preserve backward compatibility for `question_submission` events and summaries.
- Add instrumentation in small action groups: chat/teacher-help first, then practice/generation.
- Treat failed, read-only, draft, preview, and administrative operations as non-consuming unless the taxonomy explicitly says otherwise.
- Extend reconciliation and summaries after the new events exist, keeping action-level partial/unreconciled status visible.
- Keep parent/admin account operations response changes additive and privacy-safe.
- Close with focused backend tests and privacy regression evidence; run frontend checks only if additive fields require UI/client changes.

## Phases

- [x] **Phase 227: Usage Action Taxonomy And Ledger Contract** - Define governed actions, success/skip rules, idempotency keys, privacy schema, and summary groups.
- [x] **Phase 228: Chat And Teacher-Help Ledger Instrumentation** - Record safe ledger events for existing successful chat/conversation and teacher-help request flows.
- [x] **Phase 229: Practice And Generation Ledger Instrumentation** - Record safe ledger events for existing eligible practice, lesson, assignment, and generation flows.
- [x] **Phase 230: Multi-Action Reconciliation And Account Operations Summaries** - Extend reconciliation, usage summaries, and parent/admin account operations compatibility across multiple actions.
- [x] **Phase 231: v5.11 Privacy Regression And Release Gate** - Verify focused backend behavior, privacy boundaries, docs/state, and next milestone recommendation.

## Phase Details

### Phase 227: Usage Action Taxonomy And Ledger Contract

**Goal**: Make action coverage explicit before implementation creates new usage records.
**Depends on**: v5.7 usage ledger contract, v5.9/v5.10 account operations visibility.
**Requirements**: USAGE-01
**Success Criteria**:

1. Ledger action names, usage types, summary groups, quota semantics, and success conditions are documented.
2. The taxonomy distinguishes quota-enforced actions from support-visible-only actions.
3. Idempotency key rules are defined for question, chat, hint, teacher-help, practice, lesson, assignment, and generation categories.
4. Existing question submission ledger behavior remains backward compatible.
5. Failed, read-only, draft, preview, and raw-content operations are explicitly excluded unless a later phase governs them.

### Phase 228: Chat And Teacher-Help Ledger Instrumentation

**Goal**: Add durable usage evidence for conversational help and human-help escalation where existing routes already create meaningful usage.
**Depends on**: Phase 227.
**Requirements**: USAGE-02
**Success Criteria**:

1. Existing successful chat or conversation-style backend flows record idempotent usage ledger events when governed by the taxonomy.
2. Existing successful teacher-help request flows record idempotent support-visible usage ledger events.
3. Duplicate retries do not create duplicate consumption.
4. Failed/skipped operations do not write usage events.
5. Tests prove events omit raw prompts, answers, teacher messages, provider payloads, verification codes, tokens, and private artifact keys.

### Phase 229: Practice And Generation Ledger Instrumentation

**Goal**: Add durable usage evidence for eligible practice and generation flows without counting passive reads or drafts.
**Depends on**: Phase 228.
**Requirements**: USAGE-03
**Success Criteria**:

1. Existing eligible practice, lesson, assignment, or generation flows record idempotent usage ledger events.
2. Passive reads, previews, failed attempts, incomplete drafts, and non-student administrative actions are skipped unless explicitly governed.
3. Bounded metadata supports reconciliation and support explanation without raw learning content.
4. Repeated submissions, regenerated artifacts, and retried requests use stable idempotency where route contracts allow it.
5. Tests cover representative success, skip, duplicate, and privacy-boundary cases.

### Phase 230: Multi-Action Reconciliation And Account Operations Summaries

**Goal**: Make usage summaries and parent/admin account operations explain multiple action types without breaking question quota compatibility.
**Depends on**: Phase 229.
**Requirements**: RECON-02, OPS-01
**Success Criteria**:

1. Reconciliation supports multiple action types while preserving the existing question submission counter reconciliation contract.
2. Student usage summaries include multi-action consumed totals, limits when applicable, remaining quota when applicable, and partial/unreconciled status per action or group.
3. Parent account operations payloads remain backward compatible and can surface multi-action summaries.
4. Admin account operations payloads can identify stale, partial, or unreconciled action groups without raw content exposure.
5. Focused tests cover mixed-action summaries, parent/admin contracts, question backward compatibility, and privacy boundaries.

### Phase 231: v5.11 Privacy Regression And Release Gate

**Goal**: Close v5.11 with explicit evidence that broader ledger coverage is working and privacy-safe.
**Depends on**: Phase 230.
**Requirements**: VERIFY-44
**Success Criteria**:

1. Focused backend tests pass for usage ledger, question compatibility, new instrumentation, reconciliation, and account operations.
2. Privacy regression checks cover ledger events, usage summaries, logs, and parent/admin account operations payloads.
3. Docs, roadmap, state, milestone snapshots, and release evidence are updated.
4. Any required frontend checks for additive usage summary fields pass or are explicitly not needed.
5. Deferred action types and the next milestone recommendation are documented.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 227 Usage Action Taxonomy And Ledger Contract | v5.11 | 1/1 | Complete | 2026-07-04 |
| 228 Chat And Teacher-Help Ledger Instrumentation | v5.11 | 1/1 | Complete | 2026-07-04 |
| 229 Practice And Generation Ledger Instrumentation | v5.11 | 1/1 | Complete | 2026-07-04 |
| 230 Multi-Action Reconciliation And Account Operations Summaries | v5.11 | 1/1 | Complete | 2026-07-04 |
| 231 v5.11 Privacy Regression And Release Gate | v5.11 | 1/1 | Complete | 2026-07-04 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| USAGE-01 | Phase 227 | Complete |
| USAGE-02 | Phase 228 | Complete |
| USAGE-03 | Phase 229 | Complete |
| RECON-02 | Phase 230 | Complete |
| OPS-01 | Phase 230 | Complete |
| VERIFY-44 | Phase 231 | Complete |
