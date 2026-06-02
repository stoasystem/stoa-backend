# Parent Identity And Access Contract

**Milestone:** Parent Portal Real Data Integration
**Phase:** 1 - Infrastructure and Contract Grounding
**Requirements covered:** INFRA-02, DATA-04, DATA-05
**Status:** Ready for Phase 2 implementation

## Current Evidence

| Evidence | Source | Consequence |
|----------|--------|-------------|
| Cognito access tokens are decoded and role is resolved in `get_current_user`. | `src/stoa/deps.py:76-89` decodes JWT; lines 95-104 verify issuer and access token; lines 106-162 resolve role. | Future `/parents/me/...` routes should depend on `require_role("parent")` or equivalent parent-only dependency. |
| Cognito groups map to backend roles. | `src/stoa/deps.py:106-115` maps `parents` to `parent`, `students` to `student`, `teachers` to `teacher`, `admins` to `admin`. | Parent routes should not admit admin/teacher/student roles through normal parent flows. |
| Registration creates a local UUID profile ID. | `src/stoa/routers/auth.py:121` creates `user_id = str(uuid.uuid4())`; lines 206-224 write this profile with `user_repo.put_user`. | JWT `sub` is not guaranteed to equal local `user_id`. Direct `user["sub"] == parent_id` checks are unsafe for profiles created through this registration path. |
| User profiles are stored under `PK=USER#{user_id}`, `SK=PROFILE`. | `src/stoa/db/repositories/user_repo.py:6-8` writes the user profile; lines 11-14 read by `user_id`. | Ownership checks should resolve the local profile before comparing profile-linked IDs. |
| User profiles can be resolved by email through `GSI-Email`. | `src/stoa/db/repositories/user_repo.py:17-24` queries `GSI-Email` by `email`. | This is the current compatibility bridge from Cognito identity to local profile. |
| Existing student profile resolution already handles Cognito `sub` versus local UUID mismatch. | `src/stoa/routers/students.py:19-27` documents the mismatch; lines 28-35 try direct lookup; lines 36-52 resolve Cognito email then `GSI-Email`. | Phase 2 should extract/reuse the same pattern for parent profile resolution. |
| Current parent routes compare JWT `sub` directly to path `parent_id`. | `src/stoa/routers/parents.py:20-30` checks child listing; lines 53-64 check report access. | This is not compatible with local UUID profiles unless callers pass Cognito `sub`, and it should not be the `/parents/me/...` ownership strategy. |
| Current child listing scans users by `parent_id` and `role=student`. | `src/stoa/routers/parents.py:34-40` scans table with `parent_id` and role filters. | Existing MVP access pattern is scan-based and must be paginated or replaced when scale requires. |
| `GSI-ParentId` exists with `parent_id` partition and `week_start` sort. | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:43-48`. | It is a report lookup index, not a clean child profile list index. |
| Report repository uses `GSI-ParentId` by `parent_id` and `week_start`. | `src/stoa/db/repositories/report_repo.py:11-17`. | Week-specific report lookup can stay index-backed if `parent_id` uses the resolved local parent profile ID consistently. |

## Canonical Parent Identifier Strategy

**Canonical identifier for parent ownership checks in this milestone:** the local DynamoDB parent profile `user_id`.

Rationale:

- Registration writes DynamoDB profiles with a local UUID (`src/stoa/routers/auth.py:121`, `src/stoa/routers/auth.py:206-224`).
- User repository reads profiles by that local `user_id` (`src/stoa/db/repositories/user_repo.py:11-14`).
- Existing child profile links use a `parent_id` attribute (`src/stoa/routers/parents.py:34-40`), and that should refer to the local parent profile `user_id`.
- JWT `sub` is a Cognito identity claim. It is useful for authentication but cannot be treated as equivalent to the local parent profile ID without an explicit stored mapping.

Allowed compatibility fallback:

1. Try `user_repo.get_user(user["sub"])`.
2. If not found, resolve Cognito username to email through `AdminGetUser`, matching the existing student pattern in `src/stoa/routers/students.py:36-52`.
3. Query `GSI-Email` through `user_repo.get_user_by_email(email)`.
4. Require the resolved profile to have `role == "parent"`.
5. Use `profile["user_id"]` as the parent ID for child lookup, report lookup, and ownership checks.

Recommended progressive enrichment:

- If Phase 2 touches profile writes or resolution helpers, it may store a `cognito_sub` field on the local profile after resolving it. That field should be compatibility enrichment only unless CDK/backend access patterns are updated to query it.
- Do not switch canonical ownership to Cognito `sub` during this milestone unless existing child/report records are also migrated or bridged.

## Parent Profile Resolution Algorithm

Future `/parents/me/...` routes should use this algorithm:

1. Require authenticated user role `parent`.
2. Read `claims_sub = user["sub"]` and `cognito_username = user.get("username", claims_sub)`.
3. Attempt direct profile lookup with `user_repo.get_user(claims_sub)`.
4. If direct lookup fails, call Cognito `admin_get_user(UserPoolId=settings.cognito_user_pool_id, Username=cognito_username)`.
5. Extract `email` from Cognito attributes.
6. Look up local profile using `user_repo.get_user_by_email(email)`.
7. Reject with 404 or 403 if no profile exists or `profile["role"] != "parent"`.
8. Return a resolved identity object containing:
   - `claims_sub`
   - `email`
   - `parent_user_id = profile["user_id"]`
   - `profile`

This mirrors the existing student `_resolve_profile` behavior and prevents client-provided parent IDs from controlling ownership.

## Child Lookup Access Pattern

Decision for INFRA-02 and DATA-05:

**Child lookup is accepted as scan-based MVP for this milestone unless Phase 2 elects to add a CDK-backed user-child GSI.**

Evidence:

- Current parent child listing scans profile items by `parent_id` and `role` (`src/stoa/routers/parents.py:34-40`).
- CDK defines `GSI-ParentId` with partition key `parent_id` and sort key `week_start` (`/Users/zhdeng/stoa-infra/stacks/database_stack.py:43-48`).
- Student profile items are user profiles, not weekly report items. They are not shown to have a `week_start` attribute.
- Querying `GSI-ParentId` for children would be unreliable unless all student profile link items include the GSI key attributes expected by that index.

Accepted MVP implementation path:

1. Resolve the authenticated parent to local `parent_user_id`.
2. Scan for user profile items with `role == "student"` and `parent_id == parent_user_id`.
3. Paginate the scan if the implementation keeps scan-based lookup.
4. Return an empty `items` list if no linked children exist.
5. Document scan scale risk in implementation notes and tests.

CDK-backed scalable alternative:

- Add a dedicated child lookup GSI or relationship item model only if Phase 2 proves scan-based lookup is unacceptable.
- Any new index must be added in `/Users/zhdeng/stoa-infra/stacks/database_stack.py` and consumed through environment/source-controlled code, not manually assumed.

## Report Lookup Access Pattern

Week-specific report lookup can use existing `GSI-ParentId`:

- `report_repo.get_report_by_week(parent_id, week_start)` queries `GSI-ParentId` by `parent_id` and `week_start` (`src/stoa/db/repositories/report_repo.py:11-17`).
- Phase 3 should pass the resolved local `parent_user_id`, not JWT `sub`, when looking up reports.
- Current report model requires `report_id`, `parent_id`, `student_id`, `week_start`, usage counters, weak knowledge points, and recommendations (`src/stoa/models/report.py:5-14`).
- Current milestone should return missing report state instead of raising the legacy 404 shape when no parent report exists.

The report S3 bucket is not required for DynamoDB report lookup. If report artifact reads are added, Phase 3 must first handle the `S3_REPORTS_BUCKET` CDK wiring prerequisite documented in `INFRASTRUCTURE-AUDIT.md`.

## Ownership Check Requirements

Future parent route invariant:

1. Resolve authenticated parent identity before using child IDs.
2. Never trust a client-supplied parent ID in normal parent portal flows.
3. For child listing, return only students linked to `resolved_parent.parent_user_id`.
4. For child summary/history/report, verify the requested `child_id` is linked to `resolved_parent.parent_user_id` before reading summary/history/report data.
5. Deny cross-parent child access before reading child-specific records.
6. Deny student, teacher/tutor, and admin users from normal `/parents/me/...` flows unless an explicit separate admin/support route is added.
7. Keep legacy `/parents/{parent_id}/...` routes compatible only if their ownership checks are updated to compare against resolved local profile IDs rather than raw JWT `sub`.

## Compatibility Risks

| Risk | Impact | Required Handling |
|------|--------|-------------------|
| JWT `sub` differs from local profile `user_id` | Parent list/report routes can falsely reject valid parents or allow inconsistent IDs. | Use parent profile resolution algorithm before ownership checks. |
| Existing child records may store `parent_id` as email, local UUID, or Cognito `sub` | Child list can be empty for real linked accounts. | Phase 2 should inspect seed/test records and optionally support a narrow compatibility fallback, but canonical target remains local parent `user_id`. |
| `GSI-ParentId` is report-shaped with `week_start` sort key | It is not a clean child list index. | Accept scan-based MVP with pagination or add a CDK-backed GSI if scale requires. |
| Report records may use a different parent ID convention | Week report lookup can miss existing reports. | Phase 3 should align report writes/reads to local parent `user_id` or document a compatibility fallback. |
| Report S3 bucket is not injected/granted to Lambda | Backend cannot safely read S3 report artifacts. | Keep current report lookup DynamoDB-only or add CDK wiring first. |

## Phase 2 Inputs

Phase 2 should implement:

- A shared parent profile resolver in or near `src/stoa/routers/parents.py`, following the algorithm above.
- `GET /parents/me/children` using `require_role("parent")` and the resolved local parent profile ID.
- Ownership checks based on child profile `parent_id == resolved_parent.parent_user_id`.
- Empty child list response `{ "items": [] }`.
- Tests or documented test fixtures that cover the Cognito `sub` versus local `user_id` fallback.
- No admin access through `/parents/me/...`.

Phase 2 should not implement:

- Child summary/history/report aggregation.
- Frontend integration.
- Weekly report generation.
- Report S3 artifact reads unless CDK is updated first.
