# Phase 63: Backend Release Evidence And Fixture Inventory Tooling - Context

**Gathered:** 2026-06-06
**Status:** Ready for implementation
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 63 adds backend-side release evidence tooling and safe-fixture inventory support. The work must validate or collect release evidence identifiers, render sanitized fixture status, and refuse production mutation unless an approved fixture name and explicit mutation mode are supplied.

The phase is backend-only. It must not mutate production, add AWS infrastructure, or expose private report artifact internals.

</domain>

<decisions>
## Implementation Decisions

### Tooling Shape

- Add a reusable Python service for evidence validation, redaction, fixture inventory, and mutation refusal rules.
- Add a CLI wrapper under `scripts/` so operators can validate evidence bundles and inspect fixture metadata from JSON inputs.
- Add admin-only read/validate endpoints so Phase 64 can render evidence and fixture status without inventing backend contracts later.

### Privacy

- Fail closed when private markers are present.
- Omit private artifact fields from redacted output.
- Treat fixture inventory as metadata-only: version IDs, report status, audit references, request identifiers, and privacy result only.

### Mutation Safety

- Mutation checks are refusal logic only; Phase 63 does not run mutation smoke.
- Approved fixture identity remains `stoa-safe-fixture-v2-2-rollback-2026-06-06`.
- Non-ready fixtures require cleanup/restore mode before any future mutation path.

</decisions>

<code_context>
## Existing Code Insights

- `scripts/report_artifact_safe_fixture_smoke.mjs` already refuses mutation unless fixture name, fixture identifiers, and `--mutate-safe-fixture` are present.
- `src/stoa/services/report_recovery_evidence_service.py` already sanitizes recovery evidence and omits private artifact fields.
- `src/stoa/routers/admin.py` already has admin-only report operation and metadata-only evidence endpoints.
- `tests/test_admin_report_ops.py` includes privacy marker assertions that can be mirrored for release evidence behavior.

</code_context>

<deferred>
## Deferred Ideas

- Live AWS evidence collection.
- Persisted release evidence storage.
- Compliance-grade immutable release evidence.
- Customer-data mutation smoke.

</deferred>
