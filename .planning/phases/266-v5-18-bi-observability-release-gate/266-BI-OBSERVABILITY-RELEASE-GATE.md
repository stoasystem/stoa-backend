# v5.18 BI Observability Release Gate

## Release State

`bi-observability-ready-local`

## Shipped Backend Contracts

| Route | Purpose | State |
|-------|---------|-------|
| `GET /admin/bi/taxonomy` | Shared BI taxonomy and privacy boundary | Local ready |
| `GET /admin/bi/warehouse-readiness` | Cross-product warehouse readiness, blockers, operations metadata | Local ready; live warehouse blocked by default |
| `GET /admin/bi/warehouse-export` | Bounded aggregate warehouse rows with stable idempotency key | Local ready; live warehouse blocked by default |
| `GET /admin/bi/dashboard` | Aggregate operator dashboard across usage, billing/provider, curriculum, notifications, support, release smoke, and warehouse state | Local ready |
| `GET /admin/bi/alert-routing` | Low-cardinality alert routing and runbook metadata | Local ready; live APM alerts blocked by default |

## Activation Evidence

| Area | Evidence | State |
|------|----------|-------|
| Usage/quota | Usage ledger action taxonomy and admin support/reconciliation routes | `locally_ready` |
| Billing/provider readiness | Existing Stripe/TWINT readiness and v5.17 activation smoke | `read_only_verifiable`, `live_ready`, `blocked`, or `failed` by provider config |
| Curriculum analytics | Existing aggregate metrics, warehouse export, and dashboard | `locally_ready` when metrics exist; `read_only_verifiable` when empty |
| Notifications | Existing delivery-status readiness and v5.17 notification activation smoke | `read_only_verifiable` or `blocked` by provider settings |
| Support handoff/SLA | Existing metadata-only support SLA analytics | `read_only_verifiable`; provider failures become `failed` |
| Release smoke | Existing core smoke and external activation smoke | `locally_ready` or provider-state specific |
| Live BI warehouse | `bi_warehouse_live_configured=false`, `bi_warehouse_export_enabled=false` by default | `blocked` |
| Live APM alerts | `apm_provider=""`, `apm_alert_destination_approved=false`, `apm_alerts_enabled=false` by default | `blocked` |

## Privacy Gate

The v5.18 BI contract is aggregate-only. It explicitly excludes:

- Raw prompts, answers, chat messages, teacher messages, and report artifact content.
- Provider payloads and provider secrets.
- Cognito token material, login codes, verification codes, and auth tokens.
- Private S3 keys and high-cardinality private identifiers.

## Operations Controls

| Control | Behavior |
|---------|----------|
| Disable live warehouse | Keep `bi_warehouse_export_enabled=false` or `bi_warehouse_live_configured=false`; route still returns blocked/read-only local evidence. |
| Disable live alerts | Keep `apm_alerts_enabled=false`, omit `apm_provider`, or keep `apm_alert_destination_approved=false`; alert route still returns low-cardinality routing metadata. |
| Retry export | Rerun `GET /admin/bi/warehouse-export` with the same `period` and `limit`; the `idempotencyKey` remains stable for the same schema/period/filter shape. |
| Backfill export | Call `GET /admin/bi/warehouse-export?period=<period>` for the desired period; no customer mutation occurs. |
| Partial source failure | Source is represented as `partial=true` and `state=failed` or `unknown`; export/dashboard remains support-safe. |
| Rollback | Remove or disable use of `/admin/bi/*` routes; underlying source routes remain unchanged. |

## Verification

Commands run:

```bash
uv run pytest tests/test_bi_observability.py tests/test_curriculum_analytics.py tests/test_external_activation_smoke.py tests/test_core_smoke.py
uv run pytest tests/test_bi_observability.py tests/test_usage_ledger.py tests/test_subscription_operations.py tests/test_notifications.py tests/test_external_activation_smoke.py tests/test_core_smoke.py
uv run ruff check src/stoa/config.py src/stoa/services/bi_observability_service.py src/stoa/routers/admin.py tests/test_bi_observability.py tests/test_usage_ledger.py tests/test_subscription_operations.py tests/test_notifications.py tests/test_external_activation_smoke.py tests/test_core_smoke.py
```

Results:

- Focused BI/source suite: 31 passed.
- Wider BI-composed backend suite: 83 passed.
- Ruff: all checks passed.

## Residual Limitations

- Live BI warehouse integration remains blocked until live warehouse destination, credentials, schema owner approval, and export enablement are configured.
- Live APM alert delivery remains blocked until APM provider, approved destination, and alert enablement are configured.
- Native/mobile implementation remains deferred to v5.19.
