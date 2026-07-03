# Roadmap: v5.7 Usage Ledger And Quota Reconciliation

**Status:** Active planning
**Created:** 2026-07-03
**Prior milestone:** v5.6 Effective Entitlements And Paid Access Enforcement

## Goal

Make quota-governed usage durable, queryable, and reconcilable against the existing daily counter behavior.

## Why This Is Its Own Milestone

v5.6 made effective entitlement the source of truth for plan-governed access, but usage is still mostly represented by atomic counter rows. That is enough to block over-quota actions, but not enough for support-grade explanations, reconciliation, or reliable future operations visibility.

v5.7 closes that gap by adding usage ledger events and reconciliation while keeping the current counter path stable.

## Current Reality

- Question quota enforcement uses effective entitlement from v5.6.
- Daily question usage is enforced through atomic counter rows.
- There is no durable per-use event stream for quota-governed actions.
- Parent/admin usage visibility cannot yet explain ledger-versus-counter health.

## Implementation Strategy

- Define the ledger contract and idempotency rules before writing implementation code.
- Start with question submissions as the first quota-governed ledger event.
- Keep the existing atomic counter as the enforcement primitive.
- Add reconciliation as a repeatable read-only report first.
- Expose enough parent/admin support visibility to explain usage state, while leaving the full operations console to v5.9.

## Phases

- [ ] **Phase 207: Usage Ledger Contract And Idempotency** - Define durable usage event schema, privacy boundaries, idempotency keys, write ordering, and reconciliation model.
- [ ] **Phase 208: Question Usage Ledger Recording** - Record durable usage events for successful question quota increments using the v5.6 effective entitlement snapshot.
- [ ] **Phase 209: Quota Counter Reconciliation** - Compare ledger event totals with daily counter rows and report safe reconciliation status.
- [ ] **Phase 210: Usage Visibility And Focused Tests** - Expose parent/admin usage summaries with consumed, limit, remaining, effective plan, and reconciliation state.
- [ ] **Phase 211: v5.7 Usage Ledger Release Gate** - Close v5.7 with verification evidence, docs, audit, and v5.8 handoff.

## Phase Details

### Phase 207: Usage Ledger Contract And Idempotency

**Goal**: Define the usage ledger state model before implementation.
**Depends on**: v5.6 effective entitlement resolver.
**Requirements**: LEDGER-01
**Success Criteria**:

1. Usage ledger event schema covers action, quantity, actor/student, parent context, entitlement snapshot, effective plan/source, quota period, counter key, correlation IDs, timestamps, and privacy-safe metadata.
2. Idempotency rules prevent duplicate consumed-usage rows for retries.
3. Write ordering relative to the atomic quota counter is explicit.
4. Privacy boundaries exclude raw learning content, private artifacts, provider secrets, and billing internals.
5. Reconciliation inputs and expected statuses are documented before code.

### Phase 208: Question Usage Ledger Recording

**Goal**: Persist durable ledger events for question usage without destabilizing quota enforcement.
**Depends on**: Phase 207.
**Requirements**: LEDGER-02
**Success Criteria**:

1. Successful question quota increments write durable usage ledger events.
2. Ledger events include the effective entitlement snapshot used at enforcement time.
3. Retried or repeated submissions do not double-count usage events.
4. Quota exhaustion does not create consumed-usage events.
5. Focused tests cover free, paid, manual override, pending/blocked, idempotency, and quota exhaustion paths.

### Phase 209: Quota Counter Reconciliation

**Goal**: Make counter-versus-ledger health inspectable and repeatable.
**Depends on**: Phase 208.
**Requirements**: RECON-01
**Success Criteria**:

1. Reconciliation compares daily counter rows with ledger event totals by student/action/day.
2. Reports classify matched, ledger-missing, counter-missing, and count-mismatch states.
3. Reconciliation defaults to read-only preview/report behavior.
4. Any repair behavior is deterministic, bounded, and separated from preview.
5. Tests cover matched counts, missing rows, mismatches, and repeated reconciliation runs.

### Phase 210: Usage Visibility And Focused Tests

**Goal**: Make usage and reconciliation state explainable to parents/customers and admins.
**Depends on**: Phase 209.
**Requirements**: USAGE-01
**Success Criteria**:

1. Parent/customer usage summary exposes consumed, limit, remaining, effective plan, and reconciliation status for linked students.
2. Admin/support usage summary exposes usage ledger and reconciliation status without raw question content or billing internals.
3. Existing subscription and entitlement response shapes remain backward compatible.
4. Visibility clearly marks partial, stale, or unreconciled ledger data.
5. Docs keep full operations console scope deferred to v5.9.

### Phase 211: v5.7 Usage Ledger Release Gate

**Goal**: Close v5.7 as a complete backend milestone.
**Depends on**: Phase 210.
**Requirements**: VERIFY-40
**Success Criteria**:

1. Ledger contract, recording, reconciliation, visibility, and focused tests are complete.
2. Requirements, roadmap, state, and milestone history reflect v5.7 completion.
3. Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
4. Final audit records rollout state: `usage-ledger-ready`, `blocked`, or `deferred`.
5. v5.8 email verification/login-code handoff is updated.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 207 Usage Ledger Contract And Idempotency | v5.7 | 0/1 | Active | - |
| 208 Question Usage Ledger Recording | v5.7 | 0/1 | Planned | - |
| 209 Quota Counter Reconciliation | v5.7 | 0/1 | Planned | - |
| 210 Usage Visibility And Focused Tests | v5.7 | 0/1 | Planned | - |
| 211 v5.7 Usage Ledger Release Gate | v5.7 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LEDGER-01 | Phase 207 | Planned |
| LEDGER-02 | Phase 208 | Planned |
| RECON-01 | Phase 209 | Planned |
| USAGE-01 | Phase 210 | Planned |
| VERIFY-40 | Phase 211 | Planned |

---
*Last updated: 2026-07-03 after v5.7 milestone initialization.*
