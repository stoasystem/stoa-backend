# Phase 36 Production Admin Setup

**Status:** Required before production browser smoke
**Purpose:** Create a long-lived real production admin account for STOA operations. This is not a temporary smoke-test account.

## Why This Exists

Phase 36 requires read-only production browser smoke with a real admin session. The production frontend redirects `/admin/report-operations` to `/login` when no admin session exists, and the backend login flow requires both:

- a Cognito user in the `admins` group
- a DynamoDB user profile with `role = admin`

Creating only the Cognito user is not enough because `/auth/login` infers the client/role from the DynamoDB profile by email.

## Provisioning Script

Use:

```bash
export STOA_PRODUCTION_ADMIN_PASSWORD='<secure initial password>'

python scripts/provision_production_admin.py \
  --email '<admin-email>' \
  --name '<admin display name>' \
  --confirm-production
```

Defaults:

- Region: `eu-central-2`
- Cognito user pool: `eu-central-2_Ss93YQzjJ`
- DynamoDB table: `stoa-main`
- Cognito group: `admins`
- Password source: `STOA_PRODUCTION_ADMIN_PASSWORD`

The script does not print the password.

Use a dry run first when AWS credentials are newly configured:

```bash
python scripts/provision_production_admin.py \
  --email '<admin-email>' \
  --name '<admin display name>' \
  --confirm-production \
  --dry-run
```

## Required AWS Permissions

The operator running the script needs permission for:

- `cognito-idp:AdminGetUser`
- `cognito-idp:AdminCreateUser`
- `cognito-idp:AdminSetUserPassword`
- `cognito-idp:AdminAddUserToGroup`
- `dynamodb:Query` on `stoa-main` and `GSI-Email`
- `dynamodb:PutItem` on `stoa-main`

## Safety Rules

- Do not use this script for temporary smoke users.
- Use a real named STOA operator/admin email.
- Store the initial password in a password manager or approved secret path, not in git.
- Rotate the initial password after first successful login if operational policy requires it.
- If a DynamoDB profile already exists for the email with a non-admin role, stop and investigate instead of converting it.
- If a Cognito user already exists with a non-admin custom role, stop and investigate instead of converting it.

## Browser Smoke After Setup

1. Open `https://app.stoaedu.ch/login`.
2. Log in with the provisioned admin account.
3. Open `https://app.stoaedu.ch/admin/report-operations`.
4. Verify the route loads as an admin page, not the login page.
5. Verify read-only production API calls succeed for report operations/job/audit surfaces.
6. Do not click retry, resend, start job, or cancel job actions.
7. Verify the visible UI and captured responses do not include:
   - `weekly-reports/`
   - private S3 keys
   - presigned URL markers
   - raw report JSON
   - raw report HTML
   - auth tokens

## Evidence To Record

Record only redacted evidence in `36-VERIFICATION.md`:

- Backend deploy run ID and commit SHA
- Frontend deploy run ID and commit SHA
- Smoke timestamp
- Browser route result
- Redacted admin email domain or operator identifier
- API status/request IDs
- Confirmation that no production mutation was performed
- Confirmation that private artifact markers were absent
