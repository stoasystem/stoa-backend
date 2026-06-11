# Context: Phase 138 Email Digest And Push Preference Readiness

**Phase:** 138
**Milestone:** v4.2 Production Notification Delivery Readiness
**Requirement:** NOTIFYDEL-03
**Started:** 2026-06-11

## Starting Point

Phase 137 added durable notification preferences, preference-aware realtime fanout decisions, and admin delivery status aggregates.

Phase 138 builds on that foundation by preparing digest and push expansion without sending live email or native push traffic during internal development.

## Scope

- Add a user-facing digest preview contract for currently unread digest-eligible notifications.
- Support category and time-window filtering.
- Return stable digest item fields for future email templates.
- Sanitize digest metadata so private artifact or raw content references are not exposed.
- Surface no-provider fallback state for email and push readiness.
- Keep push delivery deferred while retaining durable push preference flags from Phase 137.

## Constraints

- Production email and native push providers are not configured in this backend workspace.
- This phase must not send broad production email or push traffic.
- Frontend/native notification surfaces remain deferred to the UI/native workspace.
