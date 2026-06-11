# Phase 147 Payment Release Gate

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** VERIFY-27
**Status:** Planned

## Required Evidence

Backend quality:

- Focused subscription/payment tests.
- Relevant static checks.
- Regression evidence for manual subscription override behavior.

Checkout readiness:

- Readiness state examples.
- Paid checkout blocked by default in live mode.
- Test/local checkout behavior remains usable for internal verification.
- Rollback switch blocks new live checkout.

Webhook readiness:

- SDK-backed signature verification evidence.
- Bad signature rejection.
- Duplicate event idempotency.
- Event processing result and provider mode evidence.

Billing operations:

- Invoice/receipt metadata sample.
- Refund eligibility or handoff sample.
- Dunning state sample.
- Swiss accounting handoff sample.
- TWINT lifecycle metadata or explicit provider blocker.

Rollout state:

- Live provider credential status: redacted.
- Live charges approval status.
- Live smoke status: performed, deferred, or blocked.
- Remaining external dependencies.

## Closeout Rules

v4.4 can close locally if the implemented backend behavior passes focused verification and any live-provider blockers are explicit.

v4.4 must not claim production live-charge completion unless an approved live smoke path is executed and recorded with redacted evidence.

## Remaining Feature Queue Handoff

Expected next candidates after v4.4:

- v4.5 Support Evidence Integrations And Operations Handoff.
- v4.6 Rich Curriculum Authoring And Analytics Foundation.
- Full production notification rollout if infrastructure/provider/frontend ownership is available.
