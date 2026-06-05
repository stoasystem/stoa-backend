# Phase 38 Credential Operations: Production Admin

**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Ready for operator adoption
**Created:** 2026-06-05

## Scope

This procedure governs the long-lived production admin account used for support operations and read-only production smoke on:

```text
https://app.stoaedu.ch/admin/report-operations
```

It does not authorize temporary production admin smoke accounts or production recovery mutations.

## Production Identifiers

| Item | Value |
|------|-------|
| Admin username | `stoaedu.ad@gmail.com` |
| Credential path | AWS Secrets Manager `stoa/production/admin/stoaedu.ad@gmail.com` |
| AWS profile | `stoa-prod-admin` |
| AWS region | `eu-central-2` |
| Cognito user pool | `eu-central-2_Ss93YQzjJ` |
| Required Cognito group | `admins` |
| DynamoDB table | `stoa-main` |
| Frontend route | `https://app.stoaedu.ch/admin/report-operations` |

## Ownership

| Responsibility | Owner |
|----------------|-------|
| Credential owner | Operations owner, assign before first routine support use |
| Rotation executor | Credential owner or delegated release operator |
| Access reviewer | Product/operations lead |
| Emergency revocation approver | Product/operations lead |

If an owner has not been assigned, the credential may be used only for release verification and read-only smoke, not routine support operations.

## Rules

- Never paste the password into chat, planning files, commits, screenshots, shell history, or browser smoke output.
- Never commit Cognito tokens, browser cookies, local storage, session storage, or screenshots that expose session material.
- Use the secret-backed credential path for smoke and support login.
- Keep production browser smoke read-only unless a separate approved safe fixture and mutation plan exists.
- Verify Cognito group membership before using the account for admin-only support workflows.

## Admin Group Verification

Run this before release smoke, credential rotation, or access review:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-get-user \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com \
  --query '{Username:Username,Enabled:Enabled,UserStatus:UserStatus,Created:UserCreateDate,Modified:UserLastModifiedDate}'

AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-list-groups-for-user \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com \
  --query 'Groups[].GroupName'
```

Expected:

- User is enabled.
- User status allows login.
- Returned groups include `admins`.

Evidence to record:

- Timestamp.
- AWS account and region.
- Redacted username, for example `stoaedu.ad@...`.
- Cognito user pool ID.
- `Enabled` and `UserStatus`.
- Group membership result.
- Terminal command output with no secrets or session tokens.

## Access Review

Perform access review at least quarterly and before major recovery releases.

Checklist:

- The account is still needed for production admin operations.
- The assigned owner is current.
- The Cognito user is enabled only if support/admin operations require it.
- The user belongs to `admins`.
- No unexpected extra groups are present.
- The DynamoDB profile role is `admin`.
- The secret exists at the approved path.
- Last rotation date is within policy.
- Recent browser smoke artifacts are redacted and read-only.

DynamoDB profile verification:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws dynamodb query \
  --table-name stoa-main \
  --index-name GSI-Email \
  --key-condition-expression 'email = :email' \
  --expression-attribute-values '{":email":{"S":"stoaedu.ad@gmail.com"}}' \
  --projection-expression 'user_id,email,#role,#name,updated_at' \
  --expression-attribute-names '{"#role":"role","#name":"name"}'
```

Expected:

- Exactly one profile is returned.
- `role` is `admin`.

## Rotation Procedure

Rotate after staff change, suspected exposure, failed access review, or at the regular cadence assigned by operations.

1. Generate a new strong password in an approved password manager or secure local secret workflow.
2. Load it into shell memory without printing it.
3. Update Cognito permanent password.
4. Update AWS Secrets Manager secret value.
5. Verify login in the browser using the secret-backed path.
6. Re-run admin group verification.
7. Record redacted evidence and the rotation timestamp.

Example command shape:

```bash
export STOA_PRODUCTION_ADMIN_PASSWORD='<do-not-print>'

AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-set-user-password \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com \
  --password "$STOA_PRODUCTION_ADMIN_PASSWORD" \
  --permanent

AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws secretsmanager put-secret-value \
  --secret-id stoa/production/admin/stoaedu.ad@gmail.com \
  --secret-string "$STOA_PRODUCTION_ADMIN_PASSWORD"

unset STOA_PRODUCTION_ADMIN_PASSWORD
```

Do not run rotation commands from a shell that persists history with expanded secrets.

## Emergency Disable

Disable the account immediately if credential exposure or unauthorized use is suspected:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-disable-user \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com
```

After disable:

- Verify `Enabled=false` with `admin-get-user`.
- Revoke or rotate the secret.
- Review CloudWatch/API evidence for recent admin activity.
- Do not re-enable until a new password is set and access review passes.

Re-enable only after approval:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws cognito-idp admin-enable-user \
  --user-pool-id eu-central-2_Ss93YQzjJ \
  --username stoaedu.ad@gmail.com
```

## Read-only Browser Smoke Procedure

Use this for release verification:

1. Retrieve the credential from the approved secret path without printing it in logs.
2. Open `https://app.stoaedu.ch/login`.
3. Login as `stoaedu.ad@gmail.com`.
4. Navigate to `/admin/report-operations`.
5. Verify read-only GET calls succeed.
6. Confirm no private artifact markers appear:
   - `weekly-reports/`
   - `json_s3_key`
   - `html_s3_key`
   - `s3_key`
   - presigned URLs
   - raw report JSON
   - raw report HTML
7. Do not click retry, resend, create job, cancel job, or any other mutation control.

Evidence to record:

- Timestamp.
- Redacted username.
- Final browser URL.
- GET API paths and request IDs.
- Privacy marker check result.
- Explicit `mutations_performed=false`.

## Phase 38 Decision

The existing credential path is acceptable for v1.7 read-only smoke and support verification if operations assigns a named owner and rotation cadence before routine support use.
