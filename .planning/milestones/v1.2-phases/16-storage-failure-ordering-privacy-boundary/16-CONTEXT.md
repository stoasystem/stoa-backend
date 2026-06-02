# Phase 16: Storage Failure Ordering & Privacy Boundary - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning
**Source:** Autonomous smart-discuss path; backend failure-order and privacy audit phase.

<domain>
## Phase Boundary

This phase verifies and documents behavior around report artifact storage failures and parent access privacy. The implementation should keep existing report generation, S3 writes, DynamoDB metadata, SES delivery, and parent route behavior intact unless tests reveal a gap.

In scope:
- Prove DynamoDB report metadata is written only after both JSON and HTML S3 artifact writes succeed.
- Prove SES email is attempted only after S3 writes and metadata storage succeed.
- Prove failure after the first artifact write creates no report metadata and sends no email.
- Prove parent report responses remain backend-mediated and ownership-checked, with no S3 key/url exposure.

Out of scope:
- New retry/cleanup behavior for orphaned first artifacts.
- Deployed Lambda smoke.
- New public/presigned report artifact APIs.
- CDK IAM changes.
</domain>

<decisions>
## Locked Decisions

- Preserve current ordering: JSON S3 write, HTML S3 write, DynamoDB metadata write, SES send.
- Treat a failed second artifact write as a hard failure with no metadata and no email.
- Keep parent report APIs returning DynamoDB-backed report details only, not S3 artifact keys or direct S3 locations.
- Keep existing parent-child ownership checks before report reads.
</decisions>

<references>
## Canonical References

- `.planning/REQUIREMENTS.md` - STORAGE-05 through STORAGE-07 and PRIVACY-01 through PRIVACY-03.
- `.planning/phases/15-artifact-key-contract-helper-hardening/15-VERIFICATION.md` - artifact helper and no-ACL write proof.
- `src/stoa/services/report_service.py` - storage/email ordering.
- `src/stoa/routers/parents.py` - parent report ownership and response shape.
- `tests/test_report_flow.py` - weekly report storage failure behavior.
- `tests/test_parent_children.py` - parent report authorization and detail response tests.
</references>

<risks>
## Risks and Constraints

- A failed second S3 write can leave an orphaned JSON artifact. v1.2 accepts this until a cleanup/lifecycle policy is added; the key is deterministic, so later retries overwrite the same path.
- Privacy testing should not block the existing `/files/presign` image upload route, which is unrelated to report artifacts.
