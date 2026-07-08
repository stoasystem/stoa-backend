# Phase 372 Context

## Phase Boundary

Phase 372 inventories current real evidence sources before any pilot execution.

## Decisions

- Evidence inventory is metadata-only and must exclude secrets, tokens, private object keys, raw provider payloads, and raw student content.
- Access paths are tracked for admin, parent, student, teacher/support, provider, mobile, monitoring, and deployment.
- The phase must fail closed unless every required path is available, disabled for pilot, or explicitly not required.
- Production checks require an approved credential path before downstream pilot smoke can be trusted.

## Existing Code Insights

- `production_pilot_service` already centralizes pilot/readiness evidence contracts.
- Existing v5.35-v5.39 gates use dictionary payloads plus `assert_pilot_evidence_safe`.
- Tests live in `tests/test_production_pilot.py` and cover fail-closed defaults plus ready-state overrides.
