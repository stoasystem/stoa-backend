# Phase 257 Plan: Provider Activation Reality Audit And Release Contract

## Goal

Define exact provider activation scope from current code and current blockers.

## Requirements

- `PROVIDER-01`

## Tasks

1. Map payment, Cognito/email, notification, support-provider, and production read-only smoke readiness surfaces to concrete backend/frontend files, settings, tests, and docs.
2. Classify each provider channel as `live_ready`, `read_only_verifiable`, `safe_fixture_verifiable`, `locally_ready`, or `blocked`.
3. List required credentials, rollout flags, production endpoints, safe fixtures, and approval gates per provider.
4. Promote missing readiness/refusal evidence into Phase 258, 259, or 260 follow-up work.
5. Verify the audit contract with focused repo searches and existing readiness test inventory.

## Non-Goals

- No live customer-impacting provider mutation.
- No raw provider payloads, Cognito token material, verification codes, private learning content, report artifact keys, or secrets.
- No broad implementation changes outside evidence needed for the Phase 257 release contract.

## Verification Commands

- `rg -n "provider-readiness|rollout-controls|webhook|twint|notification|support.*provider|core-smoke|email-verification" src/stoa tests .planning`
- `.venv/bin/python -m pytest tests/test_subscription_operations.py tests/test_websocket_notifications.py tests/test_core_smoke.py -q`
- `.venv/bin/python -m ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/services/notification_service.py src/stoa/services/support_destination_service.py src/stoa/services/core_smoke_service.py tests/test_subscription_operations.py tests/test_websocket_notifications.py tests/test_core_smoke.py`
