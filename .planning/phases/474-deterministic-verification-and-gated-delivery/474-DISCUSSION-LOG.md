# Phase 474: Deterministic Verification And Gated Delivery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-18
**Phase:** 474-deterministic-verification-and-gated-delivery
**Areas discussed:** Verification pass standard, CI and deployment authority, Mypy and dependency risk policy, Immutable build and audit evidence

---

## Verification Pass Standard

| Question | Alternatives considered | Selected |
|---|---|---|
| Local and CI entry point | One common authority; shared internals with different entries; CI-only authority | One common authoritative entry point |
| Environment freshness | Fresh every formal run; provenance-checked reuse; fresh only in CI | Fresh Python 3.12 environment from `uv.lock` every formal run |
| Skip policy | Zero skip/xfail/xpass; approved exception inventory; no-new-exception baseline | Zero skip/xfail/xpass |
| Repetition and time | Two fresh runs at two fixed times; two runs plus focused future tests; twice in one environment | Two fresh full-suite runs at standard and future fixed times |

**User's choice:** Selected the strict recommended option for all four questions.
**Notes:** Both runs deny ambient AWS credentials and non-allowlisted network and record deterministic run identity. External `NOT RUN` checks never count as passed.

---

## CI And Deployment Authority

| Question | Alternatives considered | Selected |
|---|---|---|
| Automatic advancement | Auto staging/manual production; manual staging and production; fully automatic production | Auto staging, manual production |
| Production approval | Protected named approver; two approvers; any repository admin | Sole project owner may self-approve through protected environment |
| Emergency path | Verified rollback only; reduced hotfix gate; complete bypass | Verified rollback only |
| Failed production smoke | Automatic rollback; manual decision; retry then rollback | Immediate automatic rollback |

**User's choice:** The owner rejected multi-person/no-self-approval rules because STOA is currently a one-person team.
**Notes:** A hotfix is new code and still passes the full gate; only rollback to an already verified artifact is fast-tracked.

---

## Mypy And Dependency Risk Policy

| Question | Alternatives considered | Selected |
|---|---|---|
| Existing mypy debt | Exact baseline first; full zero; count-only freeze | Attempt full zero before discussing any baseline |
| Missing third-party types | Maintained stubs/typed adapter; import ignores; exclude integrations | Maintained stubs or a narrow typed adapter |
| Advisory blocking | Critical/High plus reachable Medium; Critical only; every severity | Critical/High plus reachable Medium |
| Client dependency scope | Web-first; backend-only; retain native mobile | Backend plus real Web frontend; remove native mobile from v9.0 |

**User's choice:** First attempt to repair every mypy error. If that genuinely fails, return with specific evidence before the owner considers a temporary freeze.
**Notes:** The user clarified that STOA's current product is the Web App. All known reachable Web/backend bugs and launch blockers must be closed for early testing, every retained production route must be real-service functional or intentionally disabled, and student, parent, teacher, and admin/operator journeys are all in scope. Native client development begins only after the Web product is stable.

---

## Immutable Build And Audit Evidence

| Question | Alternatives considered | Selected |
|---|---|---|
| Cross-repository candidate | One release manifest; fully independent releases; backend only | One backend/frontend release manifest |
| Promotion bytes | Build once; rebuild from same source; frontend-only rebuild | Build once and promote identical bytes for both artifacts |
| Retention | Production long-term/failed 90 days; everything 90 days; current plus previous only | Production long-term, failed/staging at least 90 days |
| Gate-failure proof | Automated failure matrix plus controlled exercise; one-time exercise; static workflow check | Automated matrix plus controlled non-production exercise |

**User's choice:** Selected the strict recommended option for all four questions.
**Notes:** The current and last known-good rollback artifacts cannot be automatically deleted.

---

## the agent's Discretion

- Exact fixed clock values, manifest schema, job names, evidence serialization, safe dependency-download allowlist, smoke endpoint set, and artifact storage mechanics, subject to the locked contracts.

## Deferred Ideas

- Native Expo/iOS/Android app work after the Web App has launched for testing and is stable.
