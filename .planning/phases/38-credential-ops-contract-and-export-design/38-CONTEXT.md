# Phase 38: Credential Ops Contract and Export Design

**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Not started
**Created:** 2026-06-05

## Goal

Turn the v1.6 production admin smoke setup into a repeatable operational procedure and design a metadata-only recovery evidence export path that can be implemented without expanding production mutation scope.

## Requirements

- ADMIN-01: production admin credential ownership, rotation, emergency disable, and access review procedure.
- ADMIN-02: Cognito admins group verification procedure that avoids exposing passwords, tokens, or session secrets.

## Scope

- Document production admin credential owner, rotation cadence, revocation, and access review.
- Verify how operators should confirm Cognito `admins` group membership using the approved AWS profile or secret-backed path.
- Inspect existing report operations repository/API/UI shapes before designing export payloads.
- Define the export field allowlist and explicit denylist for private artifact data.
- Decide whether existing Lambda, DynamoDB, and admin route resources are sufficient.

## Non-goals

- No production mutation.
- No incident-wide generation retry.
- No new recovery job type.
- No Step Functions, SQS, new table, new bucket, new Lambda, or new GSI unless Phase 38 proves existing resources are insufficient.
- No support ticket integration.
- No WORM audit storage.

## Verification Targets

- Credential ops runbook update names the secret path but never exposes secret material.
- Admin group verification procedure records redacted evidence and avoids printing passwords, access tokens, ID tokens, refresh tokens, or session cookies.
- Export design uses explicit metadata allowlists.
- Export design rejects private artifact fields including `weekly-reports/`, S3 keys, presigned URLs, raw report JSON, raw report HTML, and auth/session tokens.
- Phase 38 summary records whether backend/frontend/CDK changes are required for Phase 39.

## Starting Evidence

- v1.6 long-lived admin secret path: `stoa/production/admin/stoaedu.ad@gmail.com`.
- v1.6 production read-only browser smoke loaded `/admin/report-operations`, called production GET APIs, verified admin auth, found no private artifact markers, and performed no production mutation.
- v1.6 final audit deferred credential ownership/rotation and metadata-only export as follow-up work.
