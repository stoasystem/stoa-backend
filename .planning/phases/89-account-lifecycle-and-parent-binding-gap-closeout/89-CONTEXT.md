# Phase 89 Context: Account Lifecycle And Parent Binding Gap Closeout

## Purpose

Close the highest-priority `stoa_docs` MVP auth/account gaps without weakening Cognito security or parent-child authorization.

## Existing State

- Registration and login use Cognito clients by role and local DynamoDB user profiles.
- Registration uses Cognito `admin_create_user` and marks email as verified through the backend-admin path.
- Parent portal authorization currently depends on `student.parent_id` and a scan of student profiles.
- There is no backend forgot-password/reset endpoint.

## Safety Constraints

- Password reset must not return access tokens.
- Forgot-password must avoid account enumeration where possible.
- Parent-student binding must not trust one-sided email claims.
- Existing `student.parent_id` compatibility must be preserved for weekly reports and parent portal reads.

