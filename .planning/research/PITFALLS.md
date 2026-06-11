# v4.5 Pitfalls Research: Support Evidence Integrations

**Updated:** 2026-06-12
**Milestone:** v4.5 Support Evidence Integrations And Operations Handoff

## High-Risk Pitfalls

| Pitfall | Risk | Mitigation |
|---------|------|------------|
| Treating provider write success as package validation success | A package can be invalid or private even if a provider accepts it. | Validate privacy and destination readiness before adapter calls; record separate validation and delivery status. |
| Free-form destination URLs | Turns support handoff into SSRF/credential exfiltration risk. | Use enumerated destination modes and allowlisted configuration only. |
| Logging secrets or outbound payloads | API tokens, authorization headers, customer data, or support payloads leak into audit logs. | Store credential references, payload digests, provider IDs, and redacted diagnostics only. |
| Raw artifact attachment | Support tickets can expose S3 keys, presigned URLs, or report JSON/HTML. | Attachments disabled by default; if enabled, only redacted package JSON/markdown is allowed. |
| Duplicate ticket/email creation | Retries or repeated clicks can create multiple support cases. | Use idempotency keys and delivery records keyed by package/destination/request. |
| Provider-specific fields baked into core package schema | Zendesk/Freshdesk/Help Scout needs diverge and pollute the metadata-only package. | Keep provider mapping in adapter/config layer. |
| Missing operator status | Delivery failures become invisible and manual work continues. | Add queue/list/detail and refusal/failure filters in Phase 150. |
| Silent fallback to manual copy | Operators think delivery happened when it only generated a package. | Make manual fallback explicit with distinct statuses. |
| Rate limits and transient failures ignored | Provider failures become data loss or false success. | Classify retryable failures and expose retry state. |
| Broad CRM automation scope creep | v4.5 becomes a ticketing platform project. | Limit to one approved destination workflow plus extension seam. |

## Provider-Specific Concerns

- Zendesk: attachments are a separate upload concern; ticket field mappings vary by account.
- Freshdesk: domain/API-key setup and rate limits require explicit readiness checks.
- Help Scout: conversation creation requires mailbox/customer/thread mapping and has thread-count constraints.
- SES/shared mailbox: raw MIME construction needs careful encoding, verified sender/recipient setup, and attachment type/size controls.

## Verification Pitfalls

- Tests must prove unapproved destinations refuse before provider calls.
- Tests must prove missing credentials refuse with redacted reasons.
- Tests must prove redaction still catches credential-like operator text before delivery.
- Tests must prove queue/status records do not store secrets or raw payload bodies.
- Tests must cover provider timeout, non-2xx response, retryable failure, and idempotent retry behavior for the selected adapter.

## Architecture Guardrail

Do not remove the existing `external_write` refusal until the new destination mode has its own explicit contract, readiness checks, tests, and audit/status lifecycle. The refusal is a safety boundary, not a missing feature.
