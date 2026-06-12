# Phase 148 Support Destination Contract

**Status:** Complete
**Created:** 2026-06-12
**Requirement:** SUPPORTINT-01

## Purpose

Define the support handoff destination, readiness, payload, refusal, and downstream lifecycle contract that must exist before STOA enables provider-backed support delivery.

Phase 148 is docs/contracts only. It does not enable live third-party provider writes, choose a provider SDK, or change current route/service behavior. Existing manual package generation and refusal tests remain the executable baseline.

## Current Executable Baseline

The current backend behavior is the safety baseline for v4.5:

- `preview`, `copy`, and `download` are allowed manual modes.
- `external_write` remains a compatibility refusal mode.
- Unknown destinations fail before evidence reads.
- Refused destinations skip evidence reads.
- Support handoff packages are metadata-only and redacted.
- Audit rows store metadata and reference IDs, not raw package or provider payloads.

The current source anchors are:

- `src/stoa/services/support_handoff_service.py` for `ALLOWED_DESTINATIONS`, `REFUSED_DESTINATIONS`, package composition, privacy scanning, and `write_audit_event`.
- `src/stoa/routers/admin.py` for admin-only request handling and destination validation before evidence reads.
- `tests/test_admin_report_ops.py` for support handoff metadata, redaction, `external_write`, and unknown destination regression tests.

## Destination Modes

| Mode | Phase 148 status | Phase 149 posture | Credential path | Behavior |
|------|------------------|-------------------|-----------------|----------|
| `preview` | Existing executable manual mode | Keep as fallback | `none_required` | Generate a redacted admin preview. |
| `copy` | Existing executable manual mode | Keep as fallback | `none_required` | Generate copy-ready markdown/text. |
| `download` | Existing executable manual mode | Keep as fallback | `none_required` | Generate redacted package JSON/metadata download hints. |
| `external_write` | Existing executable refusal mode | Keep refused | `not_applicable` | Refuse direct generic external writes before evidence reads. |
| `internal_queue` | Selected first approved Phase 149 path | Implement first | `none_required` | Persist metadata-only delivery/status records inside STOA-owned storage for operator queue visibility. |
| `shared_mailbox` | Contract-defined future mode | Refused until approved | secret-backed sender/recipient config required | Send redacted summary to an approved shared mailbox after SES/mail policy exists. |
| `zendesk_ticket` | Contract-defined future mode | Refused until approved | secret-backed Zendesk domain/token/custom-field config required | Create a ticket through an allowlisted Zendesk adapter. |
| `freshdesk_ticket` | Contract-defined future mode | Refused until approved | secret-backed Freshdesk domain/API-key/custom-field config required | Create a ticket through an allowlisted Freshdesk adapter. |
| `helpscout_conversation` | Contract-defined future mode | Refused until approved | secret-backed Help Scout app/mailbox/customer/thread config required | Create a conversation through an allowlisted Help Scout adapter. |

`internal_queue` is the selected first approved Phase 149 destination path because it requires no third-party provider credentials, can persist metadata-only delivery records in STOA-owned storage, and gives Phase 150 a queue/status surface before any CRM write.

Third-party destination modes are contract-defined but unapproved. They must remain refused until a separate secret-backed credential path, provider account prerequisite, operator approval gate, adapter mapping, and tests exist.

## Readiness States

Readiness is an admin-visible computed contract, not a secret display surface.

| State | Meaning | Delivery behavior |
|-------|---------|-------------------|
| `configured` | Required config and approval gate are present for this destination. | Destination may proceed to Phase 149 delivery checks. |
| `missing` | Required config, secret reference, provider prerequisite, or approval gate is absent. | Refuse delivery and expose redacted missing fields. |
| `refused` | Destination is unsupported, unapproved, privacy-failed, or intentionally blocked. | Refuse before provider calls; skip evidence reads when mode is generic/unknown/refused. |
| `dry_run_safe` | Destination can produce a redacted package or readiness preview without external writes. | Allow manual fallback or internal dry-run metadata only. |

Readiness responses may expose:

- destination mode
- readiness state
- redacted blockers and warnings
- credential reference names
- environment variable names
- configured/missing presence flags
- secret owner role
- provider account prerequisites
- operator approval gate state

Readiness responses must not expose:

- token values
- API keys
- authorization headers
- cookies
- OAuth refresh/access tokens
- provider secret payloads
- raw request/response bodies

## Selected Phase 149 Path: `internal_queue`

The selected Phase 149 path is `internal_queue`.

| Field | Required value |
|-------|----------------|
| Credential references | `none_required` |
| Exact environment variables | `none_required` |
| Secret owner | `stoa_backend` |
| Provider account prerequisites | `none_required` |
| Operator approval gate | `SUPPORT_INTERNAL_QUEUE_APPROVED=true` or equivalent rollout config |
| Persistence prerequisite | `report_repo` support handoff delivery/status rows |
| External provider calls | `none_required` |
| Attachments | disabled by default |
| Provider object reference | internal delivery/status ID only |

If the approval gate is absent, false, or unrecognized, `internal_queue` readiness is `missing` or `refused` and delivery must not be marked as sent. Manual `preview`, `copy`, and `download` fallback remains available.

## Future Third-Party Readiness Placeholders

The future third-party modes require redacted placeholder fields until approved:

| Mode | Credential reference | Env/config placeholders | Secret owner | Provider prerequisites | Approval gate |
|------|----------------------|-------------------------|--------------|------------------------|---------------|
| `shared_mailbox` | `SUPPORT_SHARED_MAILBOX_SECRET_REF` | `SUPPORT_SHARED_MAILBOX_FROM`, `SUPPORT_SHARED_MAILBOX_TO`, `SUPPORT_SHARED_MAILBOX_REGION` | support/platform owner | verified sender/recipient policy and mail sending approval | `SUPPORT_SHARED_MAILBOX_APPROVED=true` |
| `zendesk_ticket` | `SUPPORT_ZENDESK_SECRET_REF` | `SUPPORT_ZENDESK_DOMAIN`, `SUPPORT_ZENDESK_REQUESTER_ID`, `SUPPORT_ZENDESK_FIELD_MAP_REF` | support/platform owner | approved Zendesk account, token, requester, tags, custom fields | `SUPPORT_ZENDESK_APPROVED=true` |
| `freshdesk_ticket` | `SUPPORT_FRESHDESK_SECRET_REF` | `SUPPORT_FRESHDESK_DOMAIN`, `SUPPORT_FRESHDESK_FIELD_MAP_REF` | support/platform owner | approved Freshdesk account, API key, ticket fields, rate-limit policy | `SUPPORT_FRESHDESK_APPROVED=true` |
| `helpscout_conversation` | `SUPPORT_HELPSCOUT_SECRET_REF` | `SUPPORT_HELPSCOUT_MAILBOX_ID`, `SUPPORT_HELPSCOUT_FIELD_MAP_REF` | support/platform owner | approved Help Scout app, mailbox ID, customer/thread mapping | `SUPPORT_HELPSCOUT_APPROVED=true` |

These placeholder names are contract targets, not committed runtime configuration. Later phases may refine names, but must preserve redacted reference-only behavior.

## Provider-Neutral Payload Allowlist

Delivery payloads may include only metadata already safe in a support handoff package:

- redacted summary text
- package ID
- schema version
- generated timestamp
- generated-by safe admin identifier
- reason after credential and artifact redaction
- evidence reference IDs
- section types and statuses
- validation status and privacy result
- safe tags such as `stoa`, `support-handoff`, milestone, and phase
- approved custom fields from allowlisted destination config
- correlation ID
- idempotency key
- delivery status metadata
- payload digest

Delivery payloads must not include:

- raw report JSON
- raw report HTML
- raw report artifact excerpts
- S3 object key values
- presigned URL values
- public artifact URL values
- raw provider/customer payloads
- token values
- authorization headers
- cookies
- API keys
- OAuth refresh/access tokens
- secret values

## Attachment Policy

Attachments are disabled by default for all external delivery modes.

If a later phase enables attachments, the only eligible attachment sources are generated redacted package JSON or generated redacted package markdown. Attachments must have explicit size limits, content-type limits, payload digest logging, and privacy validation before delivery.

Raw report artifacts, private storage keys, presigned URLs, provider exports, screenshots containing customer data, and raw request/response bodies are never valid attachments.

## Refusal Rules

Delivery must be refused when any of these conditions are true:

- destination mode is unknown
- destination mode is `external_write`
- destination is contract-defined but unapproved
- required approval gate is missing or false
- required credential reference is missing
- provider prerequisites are missing
- package privacy validation fails
- required evidence references are missing
- operator reason is missing
- payload denylist finds private markers
- attachment policy would be violated

Unknown destination modes and generic refused modes must fail before evidence reads. Provider-specific refused states may record redacted readiness blockers, but must not call external providers.

## Delivery Lifecycle Vocabulary

Package validation status and delivery lifecycle status are separate.

Package validation may be:

- `passed`
- `refused`
- `failed`

Delivery lifecycle may be:

- `created`
- `refused`
- `queued`
- `sent`
- `failed`
- `retried`

Delivery records should include:

- delivery ID
- package ID
- destination mode
- lifecycle status
- created timestamp
- updated timestamp
- actor
- correlation ID
- idempotency key
- retry count
- retryable flag
- provider object ID or internal delivery/status ID
- provider object URL only when approved and redacted-safe
- redacted refusal reasons
- redacted failure reasons
- privacy validation result
- evidence reference IDs
- payload digest

The payload digest is a checksum/fingerprint for audit correlation. It is not a substitute for privacy validation and must not be reversible into raw payload content.

## Idempotency Contract

Phase 149 should use an idempotency key derived from stable metadata, not raw payload text. Suitable components include:

- package ID
- destination mode
- evidence reference IDs
- correlation/request ID when present
- destination config version when present

Retries must reuse the existing delivery record unless the operator explicitly creates a new package or destination request. Privacy-failed and unapproved destinations are not retryable.

## Implementation Seams For Later Phases

Phase 149 should introduce a provider-neutral destination contract/readiness service or module. It should not pollute the core package schema with provider-specific fields.

Recommended boundaries:

- Keep `support_handoff_service.py` as the metadata-only package composition boundary.
- Keep `SupportHandoffPackageRequest` provider-neutral.
- Add future destination/readiness logic behind a contract module such as `support_destination_contract.py` or equivalent.
- Persist future delivery/status records through repository helpers near existing support handoff audit rows.
- Keep provider adapters downstream of readiness and privacy validation.

Provider adapters should accept a redacted provider-neutral command and return redacted delivery results. They should not read raw report artifacts or secret values from package sections.

## Regression Guardrails

These commands and assertions protect the contract:

```bash
rg -n "ALLOWED_DESTINATIONS|REFUSED_DESTINATIONS|write_audit_event" src/stoa/services/support_handoff_service.py
rg -n "destination_mode|Unsupported destination mode|support-handoff-package" src/stoa/routers/admin.py
rg -n "external_write|unknown_destination|redacts_free_text_credentials|composes_metadata_and_audits" tests/test_admin_report_ops.py
./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff
```

The focused regression command must stay green while Phase 148 remains docs/contracts only.

## Source Traceability

| Contract rule | Source |
|---------------|--------|
| Manual `preview`, `copy`, `download` baseline | `support_handoff_service.ALLOWED_DESTINATIONS` |
| `external_write` refusal | `support_handoff_service.REFUSED_DESTINATIONS` and `test_support_handoff_external_write_is_refused_without_evidence_reads` |
| Unknown destination fail-fast | `admin.py` destination validation and `test_support_handoff_unknown_destination_rejects_before_evidence_reads` |
| Metadata-only package/audit | `support_handoff_service.build_package`, `write_audit_event`, and `test_support_handoff_package_composes_metadata_and_audits` |
| Free-text credential redaction | `PRIVATE_FREE_TEXT_PATTERN` and `test_support_handoff_package_redacts_free_text_credentials` |
| Failed release evidence refusal | `test_support_handoff_package_refuses_failed_release_evidence` |
| Future provider constraints | `.planning/research/SUMMARY.md` and `.planning/phases/148-support-destination-contract-and-credential-readiness/148-RESEARCH.md` |

## Phase 148 Non-Goals

- No live third-party provider writes.
- No provider SDK selection.
- No direct CRM/ticket system integration.
- No two-way ticket synchronization.
- No broad customer messaging.
- No raw artifact attachment support.
- No change that weakens existing support handoff refusal, redaction, or metadata-only behavior.
