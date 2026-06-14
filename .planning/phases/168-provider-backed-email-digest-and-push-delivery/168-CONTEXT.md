# Phase 168 Context: Provider-Backed Email Digest And Push Delivery

## Starting Point

Phase 167 added live WebSocket readiness and redacted operator status. Notification delivery currently supports durable in-app events, realtime fanout, preferences, digest preview, and push-ready preference metadata. Email digest and push channels are still deferred/preview-only.

Current code surfaces:

- `notification_service.digest_preview()` selects unread digest-eligible events based on preferences.
- `notification_service.delivery_decision()` marks `email_digest` as `deferred_digest` and `push` as `deferred_push` when preferences allow them.
- `notification_repo` persists notification events and preferences.
- `notify_service.send_weekly_report_email()` shows existing SES usage for weekly reports, but notification digest delivery must be separately gated.

## Requirement

`PRODNOTIF-03` requires provider-backed digest and push behavior:

- Email digest send path supports provider configuration, scheduling/manual trigger readiness, template metadata, recipient selection, and send/refusal/failure evidence.
- Push delivery path supports provider configuration, native token readiness, token lifecycle state, preference gating, and send/refusal/failure evidence.
- Delivery decisions honor durable preferences and event category/channel rules.
- Provider responses are redacted and persisted as operator-useful delivery evidence.
- Tests cover configured/unconfigured providers, opt-out, digest selection, missing push token, provider failure, and successful delivery fixtures.

## Decisions

- Real provider mutation stays gated by explicit approval and send-enabled settings.
- Tests use injected provider send functions instead of external network calls.
- Push token records store token hashes and optional provider token references, not raw native tokens.
- Digest and push evidence is persisted on notification event metadata in redacted form.
- Existing `digest_preview()` remains non-mutating; a separate digest send function performs provider-gated attempts.

## External Handoff

Deploy/provider owners must configure:

- `NOTIFICATION_EMAIL_PROVIDER`, sender, templates, approval, and send enablement.
- `NOTIFICATION_PUSH_PROVIDER`, endpoint/reference strategy, approval, and send enablement.
- Native clients must register tokens or provider token references before push delivery can succeed.
