# Phase 149: Support Evidence Export Destination Integration - Research

**Researched:** 2026-06-12
**Domain:** FastAPI admin support handoff delivery, DynamoDB single-table metadata records, fail-closed readiness gating
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Destination Selection
- Implement `internal_queue` as the only approved Phase 149 delivery path.
- Keep `external_write` refused as a compatibility/safety mode.
- Keep `shared_mailbox`, `zendesk_ticket`, `freshdesk_ticket`, and `helpscout_conversation` refused in Phase 149 unless explicitly added by a later approved phase.
- Preserve existing manual `preview`, `copy`, and `download` behavior as fallback.

#### Readiness And Approval
- `internal_queue` readiness uses `none_required` credential references, `none_required` env vars, `stoa_backend` as secret owner, and `none_required` provider prerequisites.
- Gate `internal_queue` delivery behind `SUPPORT_INTERNAL_QUEUE_APPROVED=true` or an equivalent fail-closed runtime/config flag.
- Missing or false approval should create a refused delivery result with redacted reason; it must not be recorded as sent.
- Destination readiness and package privacy must be checked before writing delivery/status records.

#### Delivery Record
- Create provider-neutral delivery/status records with delivery ID, package ID, destination mode, status, actor, timestamps, correlation ID, idempotency key, retry count, redacted refusal/failure reasons, privacy result, evidence reference IDs, and payload digest.
- Separate package validation status from delivery lifecycle status.
- Use statuses compatible with Phase 148: `created`, `refused`, `queued`, `sent`, `failed`, and `retried`.
- For `internal_queue`, provider object reference is an internal delivery/status ID only.

#### Payload And Privacy
- Delivery payload must be generated from redacted package summary/reference data only.
- Do not store raw outbound payload bodies unless they are explicitly metadata-only and needed; prefer payload digest and summary metadata.
- Do not include raw report JSON/HTML, S3 object keys, presigned URLs, authorization headers, cookies, API keys, OAuth tokens, or provider/customer payloads.
- Attachments remain disabled.

### the agent's Discretion
The implementation may choose exact module/function names, table key shape, and route names, provided they fit existing service/repository/admin-route conventions and preserve the Phase 148 contract.

### Deferred Ideas (OUT OF SCOPE)
- Operator list/detail queue visibility belongs to Phase 150.
- Third-party ticket/mailbox delivery belongs to future approved provider phases.
- Two-way support-system synchronization, SLA analytics, and customer messaging remain out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SUPPORTINT-02 | Backend support handoff can deliver a support-safe package to one approved destination path while retaining manual fallback. | `## Summary`, `## Architectural Responsibility Map`, `## Standard Stack`, `## Architecture Patterns`, `## Don't Hand-Roll`, `## Common Pitfalls`, `## Validation Architecture` [VERIFIED: REQUIREMENTS.md] |
</phase_requirements>

## Summary

Phase 149 should be planned as a narrow backend integration that keeps the existing manual package workflow intact and adds exactly one downstream delivery path for `internal_queue`, not a generic connector framework. The current backend already enforces admin-only access, validates destination names before evidence reads, builds metadata-only support packages, runs a privacy denylist, and appends support handoff package audit rows. [VERIFIED: codebase grep]

The lowest-risk implementation seam is: keep `support_handoff_service.build_package()` as the package-composition boundary, add a small destination/readiness orchestration service downstream of package creation, and persist delivery lifecycle state through new `report_repo` helpers that follow the repo's existing `SUMMARY` plus append-only `AUDIT#...` conventions. Reusing the current DynamoDB table is standard for this repo and avoids new infrastructure. [VERIFIED: codebase grep]

The main planning hazards are idempotency and status separation. The existing `package_id` is UUID-based, so it is not sufficient on its own for duplicate delivery detection. Plan for a canonical metadata-only payload digest plus a stable idempotency key, and keep package validation status separate from delivery lifecycle status so refused/unapproved deliveries do not look like successful package generation. [VERIFIED: codebase grep] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]

**Primary recommendation:** Keep `POST /admin/reports/support-handoff-package` backward-compatible for `preview|copy|download`, and add a sibling internal delivery path that reuses the same package builder, adds a fail-closed `support_internal_queue_approved` settings gate, writes a metadata-only delivery summary plus delivery audit, and returns the existing manual response shape unchanged for manual modes. [VERIFIED: codebase grep] [ASSUMED]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Admin auth and destination input validation | API / Backend | — | Admin routes already enforce `require_role("admin")` and validate `destination_mode` in `src/stoa/routers/admin.py`. [VERIFIED: codebase grep] |
| Support package composition and privacy screening | API / Backend | — | `support_handoff_service.build_package()` constructs sections, references, validation, and privacy results before any delivery persistence. [VERIFIED: codebase grep] |
| `internal_queue` readiness gate | API / Backend | — | The approval flag is runtime configuration, similar to existing billing readiness gates derived from `Settings`. [VERIFIED: codebase grep] [CITED: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/] |
| Delivery/status persistence and idempotency lookup | Database / Storage | API / Backend | DynamoDB summary and audit rows are the repo’s standard persistence shape for mutable metadata state plus append-only event history. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/put_item.html] |
| Manual fallback (`preview`, `copy`, `download`) | API / Backend | Browser / Client | The backend already produces the manual package formats; Phase 149 must preserve those responses while adding the internal delivery path. [VERIFIED: codebase grep] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `0.136.3` [VERIFIED: local venv import] | Admin route declaration, request parsing, HTTPException flow | The current admin support handoff route already uses FastAPI request-body models and dependency-based auth. [VERIFIED: codebase grep] [CITED: https://fastapi.tiangolo.com/tutorial/body/] |
| Pydantic | `2.13.4` [VERIFIED: local venv import] | Request models such as `SupportHandoffPackageRequest` | Existing admin request contracts are Pydantic models; Phase 149 should extend them only if backward-compatible. [VERIFIED: codebase grep] [CITED: https://fastapi.tiangolo.com/tutorial/body/] |
| pydantic-settings | `2.14.1` [VERIFIED: local venv import] | Runtime approval gate via `Settings` env-backed fields | The repo already centralizes env/config in `Settings`, and Pydantic Settings reads matching env vars by field name by default. [VERIFIED: codebase grep] [CITED: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/] |
| boto3 / DynamoDB Table resource | `1.43.16` [VERIFIED: local venv import] | Conditional metadata writes and consistent delivery-summary reads | `report_repo` already uses `put_item(..., ConditionExpression=...)` for create-only rows and `get_item(..., ConsistentRead=True)` for current-summary metadata. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/put_item.html] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/get_item.html] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `9.0.3` [VERIFIED: local venv import] | Focused admin route regression coverage | Extend `tests/test_admin_report_ops.py` for `internal_queue` approval, refusal, idempotency, and manual fallback preservation. [VERIFIED: codebase grep] |
| `support_handoff_service` | existing internal module [VERIFIED: codebase grep] | Metadata-only package composition and package audit | Reuse for package creation; do not move provider/delivery rules into the package schema itself. [VERIFIED: codebase grep] |
| `report_audit_retention_service` | existing internal module [VERIFIED: codebase grep] | Request-id sanitization and canonical `sha256:` digest pattern | Reuse its request-id sanitization pattern and digest style for payload digests instead of inventing a second canonicalization scheme. [VERIFIED: codebase grep] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reusing the existing DynamoDB table | New queue table or SQS workflow | Extra infrastructure is out of scope for Phase 149, while `report_repo` already has summary/audit patterns the later queue APIs can scan. [VERIFIED: codebase grep] |
| Keeping `external_write` refused | Turning `external_write` into a generic adapter | The contract explicitly keeps `external_write` fail-closed; expanding it now would weaken the approved destination boundary. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] |
| Sibling delivery endpoint | Overloading the package endpoint response for all modes | A sibling endpoint is cleaner for backward compatibility, but exact route shape is discretionary. [VERIFIED: codebase grep] [ASSUMED] |

**Installation:** No new third-party packages are needed for Phase 149; reuse the existing FastAPI/Pydantic/boto3/pytest stack. [VERIFIED: codebase grep]

## Architecture Patterns

### System Architecture Diagram

```text
Admin request
  |
  v
FastAPI admin route
  |
  +--> validate destination_mode against allowlist/refused set
  |       |
  |       +--> unknown/refused generic mode -> 422 or refused package before evidence reads
  |
  +--> gather bounded recovery/release/fixture evidence for non-refused modes
  |
  v
support_handoff_service.build_package()
  |
  +--> package validation status
  +--> privacy result
  +--> manual output mode attachments (`copy` / `download`)
  |
  +--> manual modes (`preview|copy|download`) -> existing package audit -> response
  |
  +--> internal_queue mode
          |
          +--> readiness gate from Settings
          +--> canonical metadata-only delivery payload
          +--> payload_digest + idempotency_key
          +--> report_repo summary write / duplicate lookup
          +--> append delivery audit event
          |
          +--> return package + delivery summary
```

This keeps package composition upstream of delivery persistence and lets manual fallback remain a pure package-generation path. [VERIFIED: codebase grep] [ASSUMED]

### Recommended Project Structure

```text
src/stoa/services/
├── support_handoff_service.py          # existing metadata-only package composition
├── support_destination_service.py      # [ASSUMED] readiness + internal_queue delivery orchestration
src/stoa/db/repositories/
├── report_repo.py                      # delivery summary, idempotency lookup, append-only delivery audit
src/stoa/routers/
├── admin.py                            # existing package route + sibling internal_queue delivery entrypoint
tests/
└── test_admin_report_ops.py            # focused route-level regression coverage
```

### Pattern 1: Downstream Delivery Orchestrator

**What:** Add a small service that accepts an already-built support package, computes readiness, maps the metadata-only internal payload, and persists delivery state. Keep `support_handoff_service` limited to composition/privacy/audit for the package itself. [VERIFIED: codebase grep]

**When to use:** For `internal_queue` only in Phase 149; future provider adapters can sit behind the same seam later without rewriting the package builder. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]

**Example:**

```python
# Source: existing service split in src/stoa/services/support_handoff_service.py
package = support_handoff_service.build_package(...)
if destination == "internal_queue":
    return support_destination_service.deliver_internal_queue(
        package=package,
        actor=operator,
        request_id=request_id,
    )
support_handoff_service.write_audit_event(...)
return package
```

This preserves the package contract while making delivery lifecycle a separate concern. [VERIFIED: codebase grep] [ASSUMED]

### Pattern 2: Summary Row Plus Append-Only Audit

**What:** Store the latest delivery/status record as a `SUMMARY` row and append lifecycle changes as `AUDIT#timestamp#event_id` rows, matching the repo’s existing retention/recovery patterns. [VERIFIED: codebase grep]

**When to use:** For provider-neutral delivery records that Phase 150 will need to list/filter without reconstructing state from package audit events alone. [VERIFIED: codebase grep] [ASSUMED]

**Example:**

```python
# Source: repository conventions in src/stoa/db/repositories/report_repo.py
table.put_item(
    Item={
        "PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}",
        "SK": "SUMMARY",
        "entity_type": "SUPPORT_HANDOFF_DELIVERY",
        **delivery,
    },
    ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
)
```

This exact prefix is a planning recommendation, not an existing key. The `SUMMARY` pattern and conditional create semantics are already established. [VERIFIED: codebase grep] [ASSUMED]

### Pattern 3: Fail-Closed Settings Gate

**What:** Add `support_internal_queue_approved: bool = False` to `Settings` and compute readiness from that flag rather than from ad hoc `os.environ` reads. [VERIFIED: codebase grep] [CITED: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/]

**When to use:** Any runtime approval gate where production behavior must default to blocked until explicitly enabled. [VERIFIED: codebase grep]

**Example:**

```python
# Source: readiness style already used in src/stoa/services/subscription_service.py
def get_support_destination_readiness(settings: Settings) -> dict[str, Any]:
    approved = bool(settings.support_internal_queue_approved)
    return {
        "state": "configured" if approved else "missing",
        "blockers": [] if approved else ["support_internal_queue_not_approved"],
    }
```

The state names come from the Phase 148 contract; the exact helper name is discretionary. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] [ASSUMED]

### Anti-Patterns to Avoid

- **Reusing the existing package audit row as the only delivery record:** package generation audit and delivery lifecycle are separate concepts in the contract. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
- **Computing idempotency from `package_id` alone:** `build_package()` currently generates a UUID package ID, so duplicate requests would never collide. [VERIFIED: codebase grep]
- **Recording raw delivery payloads:** the contract and current tests both enforce metadata-only storage and redact artifact/credential markers. [VERIFIED: codebase grep] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
- **Turning refused/unapproved deliveries into package-generation success:** SUPPORTINT-02 requires refused/failed delivery records, not silent success with a package attached. [VERIFIED: REQUIREMENTS.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Runtime approval config | Ad hoc `os.environ` parsing scattered through services | `Settings` / `get_settings()` | The repo already centralizes config there, and Pydantic Settings handles env-backed booleans predictably. [VERIFIED: codebase grep] [CITED: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/] |
| Payload canonicalization | A bespoke string concatenation hash | `json.dumps(..., separators=(",", ":"), sort_keys=True)` + `sha256:` digest pattern | `report_audit_retention_service._digest()` already uses this pattern, reducing mismatch risk between digest producers. [VERIFIED: codebase grep] |
| Delivery persistence | New tables/queues for the first internal path | Existing DynamoDB table via `report_repo` helpers | The repo already uses single-table summary/audit rows for adjacent operational metadata. [VERIFIED: codebase grep] |
| Generic provider adapter framework | A multi-provider abstraction in Phase 149 | One `internal_queue` branch behind a provider-neutral seam | The approved scope is one internal path plus manual fallback; broader adapter work is deferred. [VERIFIED: .planning/phases/149-support-evidence-export-destination-integration/149-CONTEXT.md] |

**Key insight:** The repo already has the right primitives for Phase 149: admin route auth, metadata-only package composition, redaction/privacy enforcement, sanitized request IDs, canonical SHA-256 digests, and conditional DynamoDB summary/audit writes. The plan should compose those pieces, not invent a parallel framework. [VERIFIED: codebase grep]

## Common Pitfalls

### Pitfall 1: Treating Package Validation As Delivery Success

**What goes wrong:** A package can be composed successfully while delivery should still be `refused` because readiness is blocked or privacy failed. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]

**Why it happens:** The current route always returns a package and writes a package audit event, so it is easy to stop there and forget the separate lifecycle vocabulary. [VERIFIED: codebase grep]

**How to avoid:** Create a delivery summary/audit path that runs after package creation and maps to `created|refused|queued|sent|failed|retried` independently of `validation.status`. [VERIFIED: .planning/phases/149-support-evidence-export-destination-integration/149-CONTEXT.md]

**Warning signs:** Delivery rows only contain `generated`/`refused`, or no explicit readiness blocker is stored. [VERIFIED: codebase grep] [ASSUMED]

### Pitfall 2: Non-Deterministic Idempotency

**What goes wrong:** Duplicate button clicks or retried requests create multiple internal queue records for the same evidence package. [VERIFIED: REQUIREMENTS.md]

**Why it happens:** `package_id` is generated with `uuid4()`, so any idempotency scheme keyed only on package identity will miss duplicates. [VERIFIED: codebase grep]

**How to avoid:** Derive `payload_digest` from the canonical metadata-only delivery payload and derive `idempotency_key` from stable fields such as destination mode, payload digest, sanitized request ID, and destination config version when present. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] [ASSUMED]

**Warning signs:** Two identical requests produce different delivery IDs with the same evidence references and same request ID. [ASSUMED]

### Pitfall 3: Leaking Private Markers Into Delivery Rows

**What goes wrong:** Delivery summaries or failure reasons capture report artifact keys, presigned URLs, or credential-like free text. [VERIFIED: codebase grep]

**Why it happens:** It is easy to serialize the whole package or whole request body instead of a filtered delivery payload. [VERIFIED: codebase grep]

**How to avoid:** Store only summary metadata, reference IDs, privacy result, refusal/failure reason, and digest. Re-run the privacy denylist on the delivery payload before persistence. [VERIFIED: codebase grep] [VERIFIED: .planning/phases/149-support-evidence-export-destination-integration/149-CONTEXT.md]

**Warning signs:** `weekly-reports/`, `json_s3_key`, `html_s3_key`, `access_token`, `cookie`, or presigned URL fragments appear in serialized test output. [VERIFIED: codebase grep]

### Pitfall 4: Breaking Manual Fallback While Adding Delivery

**What goes wrong:** Phase 149 changes the response contract or behavior for existing `preview`, `copy`, and `download` consumers. [VERIFIED: REQUIREMENTS.md]

**Why it happens:** The current route already owns package composition, so overloading it for all destinations is tempting. [VERIFIED: codebase grep]

**How to avoid:** Keep manual modes on the current path and response shape; add internal delivery as a sibling route or a strictly additive branch with mode-specific response fields only for `internal_queue`. [VERIFIED: codebase grep] [ASSUMED]

**Warning signs:** Existing support handoff route tests need unrelated fixture changes for `copy`/`download` assertions. [VERIFIED: codebase grep] [ASSUMED]

## Code Examples

Verified patterns from current sources:

### Existing Destination Gate Before Evidence Reads

```python
# Source: src/stoa/routers/admin.py
destination = body.destination_mode.strip()
if destination not in support_handoff_service.ALLOWED_DESTINATIONS | support_handoff_service.REFUSED_DESTINATIONS:
    raise HTTPException(status_code=422, detail=f"Unsupported destination mode: {destination or 'missing'}")

if destination not in support_handoff_service.REFUSED_DESTINATIONS:
    recovery_sections = [...]
```

This is the exact behavior that Phase 149 must preserve for unknown/refused generic modes. [VERIFIED: codebase grep]

### Existing Package Audit Pattern

```python
# Source: src/stoa/services/support_handoff_service.py
event = {
    "event_id": uuid4().hex,
    "event_at": now_iso(),
    "package_id": package["package_id"],
    "result": "refused" if package["destination"]["status"] == "refused" else "generated",
    "correlation_id": request_id,
}
report_repo.put_support_handoff_audit_event(package["package_id"], event)
```

Phase 149 should keep this package audit and add a separate delivery summary/audit, not replace it. [VERIFIED: codebase grep]

### Existing Canonical Digest Pattern

```python
# Source: src/stoa/services/report_audit_retention_service.py
def _digest(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
```

Use this canonicalization style for support-delivery payload digests so duplicate detection is stable. [VERIFIED: codebase grep]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `preview`, `copy`, `download` plus `external_write` refusal only | Add one approved `internal_queue` delivery path behind readiness/privacy/idempotency checks while preserving manual fallback | Phase 149 planning scope, following the Phase 148 contract completed on 2026-06-12 | Enables backend-managed support handoff status without enabling third-party writes. [VERIFIED: codebase grep] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-01-SUMMARY.md] |

**Deprecated/outdated:**

- Using `external_write` as a future generic provider path is outdated for v4.5; the contract keeps it as a refusal mode. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
- Treating support handoff package audit rows as sufficient status visibility is outdated for Phase 149 and Phase 150 because SUPPORTINT-02/03 now require provider-neutral delivery records. [VERIFIED: REQUIREMENTS.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A sibling delivery endpoint is preferable to overloading the existing package route for all modes. | `## Summary`, `## Architecture Patterns`, `## Common Pitfalls` | Low: exact route can still be chosen during planning if backward compatibility is preserved. |
| A2 | Delivery summary rows should use a dedicated prefix such as `SUPPORT_HANDOFF_DELIVERY#{delivery_id}` with `SK=SUMMARY` plus append-only delivery audit rows. | `## Architecture Patterns` | Medium: a different key prefix is viable, but planner must still preserve scan-friendly summary/audit conventions. |
| A3 | The first successful `internal_queue` lifecycle state should be `queued` rather than `sent`, because the row represents operator queue intake. | `## Open Questions`, `## Validation Architecture` | Medium: if the team wants `sent`, downstream queue/status semantics and tests will differ. |
| A4 | `idempotency_key` should be derived from destination mode + canonical payload digest + sanitized request ID/config version, not from `package_id` alone. | `## Common Pitfalls`, `## Code Examples` | Medium: if a different stable key is chosen, duplicate detection tests must be adjusted accordingly. |

## Open Questions (RESOLVED)

1. **Should a successful `internal_queue` write return `queued` or `sent`?**
   - What we know: The contract vocabulary includes both, and the selected destination is explicitly an internal queue/status record rather than a third-party dispatch. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
   - Resolution: Use `queued` for the first successful `internal_queue` persistence state. `internal_queue` represents STOA-owned operator queue intake, not a completed third-party dispatch, so `sent` remains reserved for future external provider adapters.
   - Decision source: Phase 148 selected `internal_queue` as an internal delivery/status ID path and Phase 149 plans Phase 150 queue visibility from those records.

2. **Should the frontend/backend reuse the package route or call a sibling delivery route?**
   - What we know: The current route is named and shaped as a package generator, and manual fallback must remain backward-compatible. [VERIFIED: codebase grep]
   - Resolution: Add a sibling admin delivery route for Phase 149, tentatively `POST /admin/reports/support-handoff-delivery`, and leave `POST /admin/reports/support-handoff-package` unchanged for manual fallback and existing refusal behavior.
   - Decision source: Phase 149 backward-compatibility requirement and the Phase 148 contract's distinction between package validation and delivery lifecycle status.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python runtime | Backend service code and tests | ✓ | `3.14.5` [VERIFIED: local venv import] | — |
| FastAPI / Pydantic / pydantic-settings / boto3 | Existing admin route, settings, repo patterns | ✓ | `FastAPI 0.136.3`, `Pydantic 2.13.4`, `pydantic-settings 2.14.1`, `boto3 1.43.16` [VERIFIED: local venv import] | — |
| pytest | Focused admin route regression command | ✓ | `9.0.3` [VERIFIED: local venv import] | — |
| DynamoDB service | Production persistence target | not required for focused route tests | repo uses boto3 table helpers [VERIFIED: codebase grep] | Unit tests monkeypatch `report_repo` helpers instead of requiring a live table. [VERIFIED: codebase grep] |

**Missing dependencies with no fallback:**

- None for planning or focused test execution. [VERIFIED: local venv import]

**Missing dependencies with fallback:**

- None. [VERIFIED: local venv import]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` [VERIFIED: local venv import] |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) [VERIFIED: codebase grep] |
| Quick run command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` [VERIFIED: command run] |
| Full suite command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py` [VERIFIED: codebase grep] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SUPPORTINT-02 | Approved `internal_queue` request writes a metadata-only delivery record and returns delivery lifecycle fields while preserving package privacy. | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k internal_queue_approved` | ❌ add in existing file |
| SUPPORTINT-02 | Missing/false `SUPPORT_INTERNAL_QUEUE_APPROVED` yields a refused delivery result, not sent/generated success. | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k internal_queue_requires_approval` | ❌ add in existing file |
| SUPPORTINT-02 | Privacy-failed package refuses delivery and does not persist a queued/sent record. | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k internal_queue_privacy_refusal` | ❌ add in existing file |
| SUPPORTINT-02 | Duplicate request with same stable metadata reuses the existing delivery record/idempotency key. | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k internal_queue_idempotent_duplicate` | ❌ add in existing file |
| SUPPORTINT-02 | Existing `preview`, `copy`, and `download` behaviors remain unchanged. | route/regression | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` | ✅ existing coverage |

### Sampling Rate

- **Per task commit:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff`
- **Per wave merge:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py`
- **Phase gate:** Focused support handoff tests must be green before `$gsd-verify-work`

### Wave 0 Gaps

- None for infrastructure; existing pytest and `tests/test_admin_report_ops.py` are sufficient for Phase 149. [VERIFIED: codebase grep] [VERIFIED: command run]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing Cognito/JWT auth plus admin-only `require_role("admin")` route dependency. [VERIFIED: codebase grep] |
| V3 Session Management | no | This phase does not introduce session state; it reuses existing bearer-token auth. [VERIFIED: codebase grep] |
| V4 Access Control | yes | Destination delivery remains admin-only and unknown/unapproved destinations fail closed. [VERIFIED: codebase grep] [VERIFIED: REQUIREMENTS.md] |
| V5 Input Validation | yes | Pydantic request models and explicit destination allowlist/refused checks. [VERIFIED: codebase grep] [CITED: https://fastapi.tiangolo.com/tutorial/body/] |
| V6 Cryptography | yes | Use one-way `sha256:` digests for payload correlation only; never treat digesting as a substitute for privacy validation. [VERIFIED: codebase grep] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Raw artifact or secret leakage in delivery rows | Information Disclosure | Reuse metadata-only package builder, privacy denylist, and store digest/summary instead of raw payloads. [VERIFIED: codebase grep] |
| Duplicate delivery rows from retries or repeated clicks | Denial of Service / Repudiation | Stable idempotency key plus conditional write or duplicate lookup before creating a second summary row. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] [ASSUMED] |
| Unauthorized support delivery | Elevation of Privilege | Keep admin-only route dependency and do not expose a public delivery surface. [VERIFIED: codebase grep] |
| Misleading lifecycle status for blocked destinations | Tampering / Repudiation | Separate readiness refusal from package generation and persist explicit `refused` lifecycle metadata. [VERIFIED: REQUIREMENTS.md] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/149-support-evidence-export-destination-integration/149-CONTEXT.md` - locked Phase 149 scope, delivery record fields, approval gate, manual fallback requirement.
- `.planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md` - canonical readiness, payload, refusal, lifecycle, and idempotency contract for Phase 149.
- `.planning/phases/148-support-destination-contract-and-credential-readiness/148-01-SUMMARY.md` - confirms the Phase 148 contract was completed and selected `internal_queue`.
- `.planning/REQUIREMENTS.md` - SUPPORTINT-02 acceptance criteria.
- `src/stoa/services/support_handoff_service.py` - existing package builder, privacy screening, manual output modes, package audit.
- `src/stoa/routers/admin.py` - existing request model, route shape, request-id sanitization hook, admin-only route behavior.
- `src/stoa/db/repositories/report_repo.py` - existing single-table summary/audit patterns, support handoff audit helpers, conditional write conventions.
- `tests/test_admin_report_ops.py` - executable regression baseline for admin-only support handoff behavior.
- FastAPI request body docs - https://fastapi.tiangolo.com/tutorial/body/
- Pydantic Settings docs - https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- Boto3 DynamoDB `put_item` docs - https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/put_item.html
- Boto3 DynamoDB `get_item` docs - https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/get_item.html

### Secondary (MEDIUM confidence)

- Local virtualenv version probe (`python`, `fastapi`, `pydantic`, `pydantic-settings`, `boto3`, `pytest`) - confirms runtime versions available in this workspace. [VERIFIED: local venv import]

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH - all stack claims are verified from local runtime, codebase use, or official docs.
- Architecture: HIGH - recommendations are tightly constrained by existing code seams and the Phase 148/149 contract; only route/key naming details remain discretionary.
- Pitfalls: HIGH - they are grounded in the existing UUID package ID, current package-vs-delivery split, current privacy tests, and the explicit contract language.

**Research date:** 2026-06-12
**Valid until:** 2026-07-12
