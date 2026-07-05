# Phase 263 Summary

Implemented `src/stoa/services/bi_observability_service.py` and admin endpoints:

- `GET /admin/bi/taxonomy`
- `GET /admin/bi/warehouse-readiness`
- `GET /admin/bi/warehouse-export`

The export contract is aggregate-only, bounded by `limit`, and includes a stable `idempotencyKey` for the same period/schema/filter shape. Live warehouse activation is explicit and blocked by default through `bi_warehouse_live_configured` and `bi_warehouse_export_enabled`.
