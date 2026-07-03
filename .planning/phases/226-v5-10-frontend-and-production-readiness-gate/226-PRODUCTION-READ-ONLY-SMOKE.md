# v5.10 Production Read-Only Smoke Checklist

## Preconditions

- Use approved production/staging smoke accounts only.
- Confirm no tester will create or mutate live payment/provider records.
- Confirm frontend and backend deployments point at the same environment.
- Capture timestamp, build identifiers, account IDs, and operator initials in the smoke log.

## Smoke Steps

1. Login and auth lifecycle visibility
   - Open `/login`.
   - Sign in with an approved smoke account.
   - Confirm successful role landing.
   - For a preconfigured pending-verification account, confirm the UI surfaces email verification required state without granting app access.

2. Email verification UI
   - Confirm resend/confirm UI is visible for the pending-verification account.
   - Do not send repeated real emails; run at most one approved resend if the environment owner authorizes it.
   - Confirm invalid/expired code copy is safe and does not expose internals.

3. Parent account operations
   - Sign in as an approved parent smoke account.
   - Open `/parent/account-operations`.
   - Confirm parent verification, billing status, linked child count, child binding, effective plan, and usage rows render.
   - Confirm no private learning content is shown beyond account/usage/support state.

4. Admin account operations
   - Sign in as an approved admin smoke account.
   - Open `/admin/account-operations?parentId=<approved-parent-id>`.
   - Confirm support state, parent verification, billing evidence/events, child binding, entitlement, and usage reconciliation render.
   - Confirm missing-parent lookup shows a bounded not-found message.

5. Subscription handoff
   - Open `/admin/subscriptions`.
   - Select an existing billing/request row.
   - Use `Inspect account operations`.
   - Confirm the console opens with the expected parent ID.

6. Privacy and role boundaries
   - Confirm parent route is not accessible as student/tutor/admin.
   - Confirm admin route is not accessible as parent/student/tutor.
   - Confirm API failures show generic unavailable copy without stack traces.

## Pass Criteria

- All smoke steps are completed without live mutations beyond explicitly approved email resend.
- Parent and admin views match backend account operations support state.
- No private learning content or backend internals are exposed.

## Fail Criteria

- Incorrect role can access parent/admin account operations.
- Account operations view falls back to demo data after backend failure.
- Parent/admin support state mismatches backend response.
- Private child learning content appears in account operations.
