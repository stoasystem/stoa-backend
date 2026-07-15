# Phase 472: Optional User Setup for External Evidence

**Generated:** 2026-07-15  
**Phase:** 472-privileged-identity-and-student-resource-authorization  
**Status:** Incomplete (optional; local Phase 472 verification does not require this)

Complete these items only if a separately approved non-production Cognito evidence run is desired. Do not use production credentials or authorize production mutation through this file.

## Approval and Environment

- [ ] Obtain explicit approval naming the non-production Cognito sandbox, permitted read/test operations, retention window, and cleanup owner.
- [ ] Confirm the sandbox contains no production identities or student content.
- [ ] Use a temporary operator profile restricted to the approved sandbox and operations.

## Environment Variables

Retrieve these from the approved sandbox configuration; never paste values into planning evidence or commit them.

| Status | Variable | Source | Add to |
| --- | --- | --- | --- |
| [ ] | `AWS_REGION` | Approved sandbox account/region | Local untracked environment only |
| [ ] | `COGNITO_USER_POOL_ID` | Cognito sandbox user pool | Local untracked environment only |
| [ ] | `COGNITO_STUDENT_CLIENT_ID` | Sandbox student app client | Local untracked environment only |
| [ ] | `COGNITO_PARENT_CLIENT_ID` | Sandbox parent app client | Local untracked environment only |
| [ ] | `COGNITO_TEACHER_CLIENT_ID` | Sandbox teacher app client | Local untracked environment only |
| [ ] | `COGNITO_ADMIN_CLIENT_ID` | Sandbox admin app client | Local untracked environment only |
| [ ] | `COGNITO_ALLOWED_ISSUERS` | Exact sandbox issuer allowlist | Local untracked environment only |
| [ ] | `COGNITO_ACCESS_CLIENT_IDS` | Exact approved access-client allowlist | Local untracked environment only |

## Evidence Checklist

- [ ] Read-only inventory of sandbox app clients and canonical STOA groups.
- [ ] Allowed-client versus wrong-client real-token check against the same protected endpoint.
- [ ] One teacher invitation activation and replay check using a disposable sandbox identity.
- [ ] Suspension check using an old still-valid sandbox token.
- [ ] JWKS rotation only if the sandbox exposes a safe approved mechanism; otherwise leave NOT RUN.
- [ ] Privileged reconciliation is dry-run only unless a separate mutation approval is granted.

For every executed item, record only redacted identifiers, UTC time, exact command/procedure, outcome, and cleanup. Items without approval/configuration remain `NOT RUN — approval/configuration unavailable`.

## Cleanup

- [ ] Remove disposable sandbox identities, invitations, sessions, and temporary operator access created by the approved run.
- [ ] Revoke temporary credentials and confirm no production/provider mutation occurred.
- [ ] Update `docs/security/phase-472-evidence.md` without tokens, passwords, raw subjects/emails/messages, student content, object keys, or production identifiers.

---

**Once all approved items are complete:** mark status as `Complete`. Completion does not itself approve beta or production rollout.
