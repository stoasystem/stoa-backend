# Phase 472: User Setup Required

**Generated:** 2026-07-15  
**Phase:** 472-privileged-identity-and-student-resource-authorization  
**Status:** Incomplete (required before production rollout; local verification does not require it)

Complete the production audit-key setup before rollout. The Cognito evidence items remain optional unless a separately approved non-production run is desired. Do not use production credentials for sandbox evidence or authorize production mutation through this file.

## Production Authorization Audit Keyring

- [ ] Generate a unique active HMAC key with a cryptographically secure generator and store it in the approved production secret manager.
- [ ] Use at least 32 random bytes encoded as `base64:<strict-base64>` or `hex:<strict-hex>`; do not use memorable text, repeated material, examples, defaults, or placeholders.
- [ ] Assign a unique trimmed key ID. During rotation, retained IDs and decoded key bytes must each remain unique.
- [ ] Configure retained keys only for the bounded replay-recognition window, then remove them under the approved rotation procedure.

| Status | Variable | Source | Add to |
| --- | --- | --- | --- |
| [ ] | `AUTHORIZATION_AUDIT_ACTIVE_KEY_ID` | Approved rotation record | Production secret/config deployment |
| [ ] | `AUTHORIZATION_AUDIT_ACTIVE_KEY` | Approved secret manager | Production secret deployment only |
| [ ] | `AUTHORIZATION_AUDIT_PREVIOUS_KEYS` | Approved retained-key map | Production secret deployment only |

Never paste key material into planning evidence, logs, commits, tickets, or chat. A failed startup must report only an `authorization_audit_key_*` category.

### Local verification

```bash
.venv/bin/python -m pytest -q tests/test_authorization_audit.py \
  -k 'production or key or secret or rotation or duplicate or weak or placeholder'
```

Expected: all selected tests pass; no external service or production secret is accessed.

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
