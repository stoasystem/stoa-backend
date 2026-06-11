# Requirements: v4.4 Live Payment Provider Rollout

**Milestone:** v4.4
**Status:** Complete
**Created:** 2026-06-11

## Goal

Move STOA's local Stripe-first payment provider MVP toward controlled live rollout and operator-ready billing operations. v4.4 should close the highest-value payment gaps from `stoa_docs`: live provider credential readiness, production checkout/webhook verification, Stripe-backed TWINT inclusion, refunds/invoices/tax handoff, dunning readiness, and clear release evidence.

Because STOA is still in internal development, this milestone prioritizes feature construction and practical payment-ops readiness over broad security/compliance expansion. Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

## Requirements

### PAYLIVE-01 Live Payment Rollout Contract And Credential Readiness

Implementers have a concrete rollout contract before live payment behavior is enabled.

Acceptance criteria:

- Contract identifies Stripe live-mode credential path, webhook endpoint expectations, price/product mapping, environment variables, and rollback switches.
- Contract records how TWINT is included through Stripe for v4.4, what account or capability checks are required, and which rollout gates still block real customer use.
- Contract defines safe smoke modes: local/test-mode verification, approved live-mode configuration inspection, and explicit no-real-charge default.
- Contract maps existing checkout/status/webhook code paths to the required production rollout changes.
- `stoa_docs` gap audit and remaining feature queue mark live payment rollout as the active v4.4 build area.

### PAYLIVE-02 Production Checkout And Webhook Verification

Backend payment APIs and operator checks are ready for production checkout/webhook rollout.

Acceptance criteria:

- Checkout session creation can distinguish configured live-mode readiness from test-mode/local behavior and expose whether TWINT-capable Stripe Checkout is eligible for Swiss/CHF subscription flows.
- Webhook verification records provider mode, event type, processing result, idempotency status, and relevant request/correlation identifiers.
- Admin billing visibility exposes enough provider status for internal operators to verify checkout and webhook lifecycle without inspecting provider secrets.
- Tests cover live-readiness configuration behavior, webhook idempotency, failure states, and non-live fallback behavior.
- No real customer charge is attempted without explicit rollout approval.

### PAYLIVE-03 Refunds Invoices Tax And Dunning Readiness

Billing operations have first-pass functional support or clear integration-ready contracts.

Acceptance criteria:

- Refund readiness contract identifies eligible billing states, required operator inputs, provider handoff behavior, and audit/status fields.
- Invoice/receipt readiness contract identifies provider-hosted invoice links or metadata fields that can be surfaced to parents/admins.
- Tax/accounting handoff defines exportable billing metadata needed for Swiss accounting workflows.
- Dunning readiness defines overdue/payment-failed states, parent/admin visibility, and retry/escalation boundaries.
- Billing projections and operator flows handle Stripe-backed TWINT subscription and refund lifecycle data through the same invoice, refund, and dunning surfaces.
- Tests or documented fixtures cover state transitions and operator-visible outputs for the implemented readiness scope.

### VERIFY-27 v4.4 Payment Release Gate And Support Audit

v4.4 closes with focused payment evidence and an updated remaining-feature audit.

Acceptance criteria:

- Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v4.4 payment work.
- Release evidence includes available backend/frontend build evidence, provider configuration checks, webhook verification evidence, and explicit live-charge deferral or approval status.
- Final audit lists remaining payment work: broader provider automation, accounting integration, expanded refund/dunning automation, and any TWINT rollout gaps still blocked by provider capability or approval state.
- The next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Support-ticket/evidence destination integrations after approved connector or credential path exists.
- Rich curriculum authoring workflow, production content QA, analytics dashboards, and deeper operations reporting.
- Full production notification rollout beyond backend readiness once infrastructure/provider/frontend ownership is available.
- Native mobile app rollout and full localization governance beyond the selected v4.3 frontend scope.
- Multi-provider billing automation beyond Stripe/TWINT basics.

## Out of Scope

- Real production customer charges without explicit approval.
- Broad CRM, accounting, or marketing automation.
- Replacing provider-hosted billing primitives where provider metadata/links are sufficient for rollout.
- Broad security/compliance test expansion unrelated to touched payment paths.
- Native app payment flows unless a native workspace is selected.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYLIVE-01 | Phase 144 | Complete |
| PAYLIVE-02 | Phase 145 | Complete |
| PAYLIVE-03 | Phase 146 | Complete |
| VERIFY-27 | Phase 147 | Complete |
