# Phase 262 Analytics Reality Audit

## Existing Surfaces

| Surface | Code | Existing Route/Test | BI State |
|---------|------|---------------------|----------|
| Usage/quota ledger | `src/stoa/services/usage_ledger_service.py` | `GET /admin/usage/students/{student_id}`, `GET /admin/usage/reconciliation`, `tests/test_usage_ledger.py` | `locally_ready` for governed action taxonomy; per-student inspection remains support-only |
| Billing/provider readiness | `src/stoa/services/subscription_service.py` | `GET /admin/subscriptions/billing/provider-readiness`, `tests/test_subscription_operations.py` | `live_ready`, `read_only_verifiable`, `blocked`, or `failed` depending on Stripe/TWINT config |
| Curriculum analytics/warehouse | `src/stoa/services/curriculum_analytics_service.py` | `GET /admin/curriculum/analytics/warehouse-readiness`, `warehouse-export`, `dashboard`, `tests/test_curriculum_analytics.py` | `locally_ready` when aggregate metrics exist; `read_only_verifiable` when empty |
| Teacher help and support | `src/stoa/services/support_sla_service.py`, usage ledger teacher-help actions | `GET /admin/reports/support-handoff-sla`, usage ledger tests | `read_only_verifiable` locally; provider failures become `failed` |
| Notifications | `src/stoa/services/notification_service.py` | `GET /admin/notifications/delivery-status`, notification tests | `live_ready`, `read_only_verifiable`, or `blocked` by email/push/WebSocket provider settings |
| Support provider handoff | `src/stoa/services/support_destination_service.py`, `support_sla_service.py` | support handoff routes/tests | `read_only_verifiable`, `blocked`, or `failed` by provider/destination state |
| Core smoke | `src/stoa/services/core_smoke_service.py` | `GET /admin/core-smoke`, `tests/test_core_smoke.py` | `locally_ready` with expected external/auth blocks |
| External activation smoke | `src/stoa/services/external_activation_service.py` | `GET /admin/external-activation/*-smoke`, `tests/test_external_activation_smoke.py` | v5.17 taxonomy: live/read-only/safe-fixture/local/blocked |

## Shared Taxonomy

- `live_ready`: live provider or product signal is configured, approved, and enabled.
- `read_only_verifiable`: operators can inspect the signal without customer-impacting mutation.
- `safe_fixture_verifiable`: signal can be tested only through an approved safe fixture.
- `locally_ready`: local implementation is ready, but live provider/deploy evidence is absent.
- `blocked`: a required credential, approval, fixture, deployment, or provider state is missing.
- `failed`: a product regression or provider-call failure is present.
- `unknown`: the source could not be inspected in the current environment.

## Privacy Boundary

BI exports and dashboards may include aggregate counts, product surface names, period/filter metadata, low-cardinality status, blocker categories, support actions, generated timestamps, and privacy metadata.

They must not include raw prompts, raw answers, chat messages, teacher messages, provider payloads, Cognito token material, login/verification codes, secrets, raw report artifact content, private S3 keys, or high-cardinality private identifiers.

## Routed Gaps

- Phase 263: add cross-product aggregate warehouse export/readiness contract with idempotency, bounded rows, retry/backfill semantics, and privacy metadata.
- Phase 264: add cross-product operator dashboard API that composes usage, billing/provider, curriculum, teacher-help/support, notification, release-smoke, and warehouse status.
- Phase 265: add alert routing contract and runbook metadata for low-cardinality APM/alert integration.
