# Next Product Milestone

- **Updated:** 2026-07-14 after the full-project audit at `de3bf1e`
- **Active milestone:** v9.0 Product Reality, Authorization And Core Journey Completion
- **Mode:** internal product completion; external rollout and production mutation remain separately approved

## Current Reality

The v7.0-v8.4 sequences are complete as local gated operations contracts. They provide decision and evidence structures but do not prove integrated product completion or live rollout.

The full-project audit supersedes the previous recommendation to keep extending those gates:

- 2 P0 findings: public privileged registration and horizontal student-data access.
- 9 P1 findings across object isolation, practice integrity, transactional writes, billing, teacher concurrency, CI, mobile identity, mobile completeness, and test trustworthiness.
- 18 P2 and 2 P3 findings covering token validation, upload/logging/dependencies, mobile/API contracts, WebSocket/IaC/observability, pagination, architecture, and documentation.
- Python 3.12 and 3.14 both report 12 failed and 640 passed tests.
- The mobile dependency manifest cannot clean-install and most native routes remain placeholders.

Primary evidence:

- `docs/audit/full-project-audit.md`
- `docs/audit/findings.json`

## Active Milestone

### v9.0 Product Reality, Authorization And Core Journey Completion

**Goal:** Convert broad local backend contracts into a trustworthy, installable internal product with authorized data access, recoverable writes, real paid-access behavior, functional student/parent mobile journeys, versioned infrastructure, realtime delivery, and traceable release evidence.

**Phase sequence:**

1. Phase 472 closes privileged identity and student-resource authorization.
2. Phase 473 closes upload/privacy/practice integrity gaps.
3. Phase 474 restores deterministic verification and gated delivery.
4. Phase 475 makes learning/relationship writes transactional and concurrency-safe.
5. Phase 476 completes idempotent billing and paid-access recovery.
6. Phase 477 creates an installable, contract-correct mobile foundation.
7. Phase 478 completes real student/parent mobile journeys and login-code behavior.
8. Phase 479 versions infrastructure and integrates full WebSocket delivery.
9. Phase 480 adds observability, complete pagination, staged promotion, and rollback.
10. Phase 481 performs the product-reality gate and milestone audit.

## Selection Rules

- Do not start a separate feature milestone while either P0 remains open.
- Do not call v9.0 complete with a red Python suite, an unbuildable mobile client, or source-string-only mobile tests.
- Do not grant curriculum editing to all teachers/tutors; preserve explicit capabilities.
- Do not convert missing provider/live evidence into a passing local mock.
- Choose v9.1 only from v9.0 final evidence. No v9.1 theme is committed yet.

## Immediate Next Step

`$gsd-discuss-phase 472`

Then:

`$gsd-plan-phase 472`
