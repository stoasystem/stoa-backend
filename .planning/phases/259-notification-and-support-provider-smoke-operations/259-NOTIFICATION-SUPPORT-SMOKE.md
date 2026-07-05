# Phase 259 Notification/Support Smoke Evidence

## New Release Endpoint

- Route: `GET /admin/external-activation/notification-support-smoke`
- Role: admin only
- Mutation: none
- Secrets: redacted
- Raw provider payloads: excluded
- Customer messages/provider ticket payloads: excluded

## Notification Contract

The notification section reports:

- WebSocket endpoint, route configuration, deployment, live smoke, TTL, and stale cleanup readiness.
- Email digest provider, approval, sender, template, and send flag readiness.
- Push provider, approval, API credential presence, endpoint, template, and send flag readiness.
- Preference categories/channels and gating enforcement.
- Push token registration support without exposing raw tokens.
- Admin delivery-status evidence route.

Customer-impacting notification sends remain disabled unless provider configuration, approval, credentials, endpoint/template, live smoke, and send flags are present.

## Support Provider Contract

The support section reports:

- Internal queue approval.
- Third-party support provider approval, credentials, endpoint, failure flag, and retry max attempts.
- CRM messaging approval, destination approval, approved templates, supported destinations, and failure flag.
- Admin routes for support delivery lifecycle, SLA, retry, and provider sync.

Third-party provider writes and customer messages remain disabled unless all approval and credential gates are satisfied and a safe fixture is available.

## Fail-Closed Evidence

- Missing notification providers return notification `classification=blocked`.
- Configured notification providers with send flags disabled return `read_only_verifiable`.
- Missing support approvals/credentials return support `classification=blocked`.
- Provider/customer writes require `safeToMutate=true`; otherwise smoke mode is `read_only`.
