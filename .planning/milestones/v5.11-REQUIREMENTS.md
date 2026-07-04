# Requirements: v5.11 Additional Usage Ledger Coverage

**Milestone:** v5.11
**Status:** Planning
**Created:** 2026-07-04
**Prior milestone:** v5.10 Account Operations Frontend And Production Readiness

## Purpose

Extend the durable usage ledger beyond question submissions so paid-limit behavior, parent account explanations, and admin support views can account for the rest of the learning actions that create meaningful usage.

v5.7 established the ledger, idempotency, and reconciliation pattern for question submissions. v5.9 and v5.10 made that usage visible in parent/admin account operations. v5.11 should keep the question quota path stable while adding governed coverage for chat, hints, teacher-help requests, and practice or generation actions that should be support-visible or quota-relevant.

## Requirements

### USAGE-01 Governed Usage Action Taxonomy

Acceptance criteria:

- Ledger action names, usage types, summary groups, and success conditions are defined for chat, hints, teacher-help, and practice/generation actions.
- The taxonomy distinguishes quota-enforced actions from support-visible-only actions.
- Existing question submission ledger behavior remains backward compatible.
- Idempotency key policy is defined for each action, including retry, duplicate request, and generated artifact cases.
- Explicit non-ledger actions are documented so read-only, failed, draft, and raw-content operations do not accidentally consume usage.

### USAGE-02 Chat And Teacher-Help Ledger Instrumentation

Acceptance criteria:

- Existing successful chat or conversation-style backend flows record privacy-safe, idempotent usage ledger events when they represent billable or support-visible usage.
- Existing successful teacher-help request flows record privacy-safe, idempotent usage ledger events when they represent support-visible usage.
- Ledger events store action metadata, counters or summary linkage, request correlation, and entitlement context without raw prompts, answers, teacher messages, provider payloads, verification codes, or private artifact keys.
- Duplicate retries do not create duplicate consumption.
- Focused tests cover success, duplicate, failed/skipped, and privacy-boundary behavior.

### USAGE-03 Practice And Generation Ledger Instrumentation

Acceptance criteria:

- Existing successful practice, lesson, assignment, or generation flows that create meaningful student usage record privacy-safe, idempotent usage ledger events.
- Practice/generation instrumentation records enough bounded metadata to reconcile and explain usage without storing raw learning content or generated provider payloads.
- The implementation avoids ledger writes for passive reads, previews, failed attempts, incomplete drafts, and non-student administrative actions unless explicitly governed by the taxonomy.
- Idempotency works for repeated submissions, regenerated artifacts, and retried requests where supported by the route contract.
- Focused tests cover representative practice/generation flows, skips, duplicates, and privacy boundaries.

### RECON-02 Multi-Action Reconciliation And Usage Summaries

Acceptance criteria:

- Usage reconciliation supports multiple action types while preserving the existing question submission counter reconciliation contract.
- Student usage summaries include multi-action consumed totals, limits when applicable, remaining quota when applicable, and partial/unreconciled status per action or summary group.
- Parent usage summaries can explain non-question usage without implying those actions are always quota-limited.
- Admin/support summaries can identify stale, partial, or unreconciled action groups without exposing private content.
- Focused tests cover mixed-action summaries, question backward compatibility, and unreconciled/partial states.

### OPS-01 Parent/Admin Account Operations Compatibility

Acceptance criteria:

- Parent account operations payloads can display or pass through multi-action usage summaries without breaking the v5.10 frontend contract.
- Admin account operations payloads can display or pass through multi-action usage summaries and support warnings without exposing raw content or provider internals.
- Any frontend-facing field changes are additive or guarded so existing account operations pages keep working.
- Privacy boundaries remain explicit for parents, admins, support workflows, and logs.
- Focused backend contract tests cover parent and admin account operations after multi-action usage is enabled.

### VERIFY-44 v5.11 Usage Coverage Release Gate

Acceptance criteria:

- Focused backend tests pass for usage ledger, question quota compatibility, chat/teacher-help instrumentation, practice/generation instrumentation, reconciliation, and account operations.
- Privacy regression checks prove no raw prompts, answers, generated content, provider payloads, verification codes, tokens, or private artifact keys are stored in ledger events or usage summaries.
- Docs, roadmap, state, milestone snapshots, and next-milestone recommendations are updated.
- Any minimal frontend checks required by additive usage summary fields are run or explicitly marked not needed.
- Release evidence names the completed coverage and any deliberately deferred action types.

## Out of Scope

- Changing paid plan pricing, entitlement limits, or Stripe/TWINT activation.
- Replacing the existing atomic question counter enforcement path.
- Storing raw chat prompts, answers, teacher replies, practice content, generated artifacts, provider payloads, verification codes, auth tokens, or private artifact keys in the ledger.
- Building new native/mobile usage UI.
- Building a warehouse/BI analytics export.
- Implementing brand-new chat or hint product surfaces when no backend route exists; v5.11 instruments existing successful flows and documents future-only action types.

## Future Milestones

- Native/mobile account operations client once web and backend usage explanations are stable.
- Warehouse/BI or analytics export after the governed ledger taxonomy has enough production data.
- Rich curriculum/editor frontend implementation if product priority shifts from account operations to content authoring.
- External activation milestones for live Stripe/TWINT, support provider, notification provider, and production warehouse prerequisites.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| USAGE-01 | Phase 227 | Complete |
| USAGE-02 | Phase 228 | Complete |
| USAGE-03 | Phase 229 | Complete |
| RECON-02 | Phase 230 | Complete |
| OPS-01 | Phase 230 | Complete |
| VERIFY-44 | Phase 231 | Planned |
