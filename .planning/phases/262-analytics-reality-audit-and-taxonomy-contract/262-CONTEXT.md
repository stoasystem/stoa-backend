# Phase 262 Context: Analytics Reality Audit And Taxonomy Contract

## Goal

Define exact analytics scope from current code, current data, and v5.17 provider states before enabling cross-product BI exports or dashboards.

## Inputs

- `.planning/ROADMAP.md` Phase 262
- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/services/external_activation_service.py`
- `src/stoa/services/notification_service.py`
- `src/stoa/services/support_sla_service.py`
- `src/stoa/services/core_smoke_service.py`
- `src/stoa/routers/admin.py`

## Boundaries

- Aggregate operational analytics only.
- No raw prompts, answers, chat messages, provider payloads, tokens, secrets, private report artifact content, or private S3 keys.
- Live BI warehouse/APM activation remains blocked unless explicit config and approval exist.
