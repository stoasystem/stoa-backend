# Phase 265 Context: APM Alert Routing And Observability Runbooks

## Goal

Make product regressions and external-provider blockers alertable without leaking private data.

## Scope

- Add low-cardinality alert routing contract.
- Separate product regressions, provider blockers, read-only/local-only states, stale data, and privacy boundaries.
- Keep live alert delivery disabled unless APM provider, destination approval, and enablement flags are configured.
