# Phase 247 Plan

## Goal

Define the exact usage/quota stability contract from current backend and frontend behavior.

## Tasks

1. Map current governed usage action taxonomy and persistence helpers.
2. Audit backend usage-bearing routes and services for consume, skip, idempotency, and privacy behavior.
3. Check focused backend test evidence for each important usage class.
4. Inspect frontend entry points that can trigger the audited backend paths or render support explanations.
5. Classify each flow as both counter and ledger, ledger-only, intentionally skipped, missing, future-only, or externally blocked.
6. Derive Phase 248-250 priorities from real gaps and risks.

## Success Criteria

- Usage-bearing backend/frontend flows are mapped to concrete files, routes, services, and tests.
- Each flow is classified as ledger event, aggregate counter, both, intentionally skipped, missing, future-only, or externally blocked.
- Consume/skip rules for failed, preview, dry-run, admin, duplicate, and provider-blocked flows are documented.
- Phase 248-250 priority fixes are separated from BI, APM, and live-provider work.
