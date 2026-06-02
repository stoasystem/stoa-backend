# Feature Landscape: v1.2 S3 Report Artifact Infrastructure

**Domain:** private report artifact storage and verification for STOA backend
**Researched:** 2026-06-03
**Overall confidence:** HIGH for backend feature boundaries; MEDIUM for deployed CDK state until synth/diff/runtime smoke evidence is captured.

## Table Stakes

Features this milestone should include. Missing any of these leaves report artifact storage not deployable or not verifiable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| CDK reports bucket wiring verification | The milestone is explicitly about proving `S3_REPORTS_BUCKET` injection and reports bucket read/write grants for API and weekly report Lambdas. | Medium | Verify `cdk synth`/`cdk diff`, Lambda env vars, IAM grants, and no bucket replacement. Do not rely on prior planning claims without fresh evidence. |
| Backend runtime config proof | `settings.s3_reports_bucket` exists locally, but production must be CDK-injected instead of using the default `stoa-reports`. | Low | Capture local config behavior and deployed/synthesized Lambda env evidence. |
| Stable artifact key contract | The slice document recommends `reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`, while current code emits `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`. | Medium | This is the main contract gap. Either change code to the chosen contract or deliberately amend the milestone contract. Tests should assert the exact prefix, not only suffixes. |
| Canonical key builder/helper | Current artifact key generation is private to `report_service.py`; the milestone asks for a stable helper or equivalent behavior. | Medium | Prefer a small `report_artifact_service.py` or public helper that builds keys, sanitizes path segments, writes JSON/HTML, and optionally reads JSON. Keep generation/email orchestration outside it. |
| JSON and HTML artifact write behavior | Existing `store_and_send_weekly_report` writes JSON first and HTML second using `settings.s3_reports_bucket`. | Low | Preserve content types: `application/json` and `text/html; charset=utf-8`. Tests already cover writes before metadata/email; broaden them to cover full key contract. |
| Failure ordering guarantee | If S3 artifact storage fails, metadata and email should not falsely indicate a generated report. | Low | Existing flow test covers no DynamoDB/email after S3 failure. Keep this as an explicit acceptance criterion. |
| Private-object smoke behavior | Planning requires a deployed smoke proving Lambda can write/read private artifacts without public URL access. | Medium | Add a minimal smoke command/job/endpoint path that writes and reads a deterministic test object, then reports bucket/key/readback success. Prefer cleanup or a clearly namespaced smoke key. |
| Read helper for JSON artifact | The milestone asks to validate helper behavior for writes and reads. | Medium | Current parent API returns report detail from DynamoDB, not S3. A helper-level `get_report_json(s3_key)` is enough for this slice; parent routes do not need to read S3 yet. |
| Privacy and identifier hygiene | Report artifacts contain parent/student learning data and should stay private. Keys must use backend IDs, ISO week start, and no email addresses. | Low | Tests should assert keys do not include parent/student emails from payload. Backend APIs remain the access layer. |
| Evidence artifact for verification | This is a hardening milestone, so roadmap needs proof, not only implementation. | Low | Create phase output that records CDK synth/diff snippets, deployed env var confirmation, smoke result, and code/test evidence. |

## Future/Differentiators

Valuable follow-ups, but not needed for this v1.2 slice.

| Feature | Value Proposition | Complexity | Defer Reason |
|---------|-------------------|------------|--------------|
| Presigned report artifact download | Allows secure direct download for admin or support workflows. | Medium | Parent frontend should not fetch private S3 directly in this slice; current parent API already renders report state from DynamoDB. |
| Admin report artifact viewer | Helps support inspect stored JSON/HTML artifacts. | Medium | Requires admin authorization and UX decisions outside storage verification. |
| PDF report artifact | Better parent-facing archival format. | High | Explicitly out of scope; HTML/JSON are enough. |
| Object versioning or retention workflow | Improves auditability and rollback. | Medium | Useful later, but current slice only needs private write/read proof. |
| Narrow IAM prefix restrictions | Reduces blast radius versus bucket-wide read/write. | Medium | The slice accepts read/write grants for MVP; record prefix-restricted IAM as later security hardening. |
| Artifact schema versioning | Helps future report format migrations. | Low | Can be added to JSON artifact later; not required to prove storage contract unless format churn is expected immediately. |
| Operational cleanup for smoke objects | Keeps smoke artifacts from accumulating. | Low | Nice to have. For this slice, a deterministic `reports/smoke/...` or equivalent namespace is acceptable if documented. |

## Anti-features/Out of Scope

Do not include these in v1.2; they dilute the verification slice.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Rebuilding weekly report generation | v1.1 already shipped aggregation, generation, storage, SES delivery, and parent rendering. | Only touch generation flow where needed to enforce artifact helper/key contract. |
| Bedrock prompt/content changes | The milestone is infrastructure and artifact storage verification. | Leave report content behavior unchanged. |
| SES delivery changes | Email behavior is already tested around storage ordering. | Preserve existing order: S3 artifacts, metadata, then SES. |
| DynamoDB metadata model redesign | Current report metadata includes `s3_key`, `html_s3_key`, and `json_s3_key`. | Only adjust key values if contract changes. |
| Parent frontend changes | Frontend should not fetch S3 artifacts directly. | Keep parent API as the report access layer. |
| Public S3 objects or public URLs | Conflicts with private report artifact storage. | Use backend-mediated reads or future authorized presigned URLs. |
| Manual AWS console fixes | Breaks CDK source-of-truth discipline. | Make all required infrastructure changes in CDK and verify with synth/diff. |
| New AWS services or buckets | Current CDK reportedly already has the reports bucket and Lambda wiring. | Reuse the existing reports bucket unless fresh CDK evidence proves it cannot support the contract. |
| Full report regeneration/admin tooling | Operationally useful, but separate from artifact storage deployment readiness. | Defer to a later operational milestone. |

## Requirement Seeds

Use these as roadmap/phase requirements for the v1.2 slice.

1. **S3ART-01: CDK reports bucket wiring is freshly verified.**
   - Evidence must show API Lambda and weekly report Lambda both receive `S3_REPORTS_BUCKET`.
   - Evidence must show both Lambdas have reports bucket read/write access.
   - Evidence must show the reports bucket is private and not being replaced by the planned deployment.

2. **S3ART-02: Backend report artifact key contract is explicit and enforced.**
   - Decide whether the canonical prefix is `reports/` or current `weekly-reports/`.
   - Tests must assert full JSON and HTML keys for parent ID, student ID, and ISO week start.
   - Keys must use canonical backend IDs and must not contain email addresses.

3. **S3ART-03: Artifact helper behavior is isolated or made equivalently testable.**
   - A helper builds canonical keys, sanitizes path segments, writes JSON, writes HTML, and reads JSON.
   - If no new module is added, current `report_service.py` behavior must expose equivalent testable functions.

4. **S3ART-04: JSON/HTML artifact writes preserve existing ordering guarantees.**
   - JSON and HTML are written to `settings.s3_reports_bucket` before DynamoDB metadata is saved.
   - SES is attempted only after artifact writes and metadata storage.
   - If either artifact write fails, report metadata and SES are not written.

5. **S3ART-05: Runtime smoke proves private write/read access.**
   - A deployed Lambda-context smoke writes a test JSON object under a reserved smoke key.
   - The same runtime reads the object back and verifies content.
   - The smoke path does not require or expose a public S3 URL.

6. **S3ART-06: Parent API remains backend-mediated.**
   - Parent routes continue returning report state/detail from authorized backend APIs.
   - No frontend direct S3 fetch is introduced.
   - Any future artifact read for parent display must happen behind existing parent ownership checks.

7. **S3ART-07: Verification results are captured for roadmap closure.**
   - Record backend tests run, CDK synth/diff results, environment verification, and smoke result.
   - Mark deployed-state confidence separately from code-state confidence if deployment is not performed.

## MVP Recommendation

Prioritize:

1. Verify CDK/env/IAM state.
2. Resolve and enforce the artifact key contract mismatch.
3. Extract or harden artifact helper behavior with focused tests.
4. Add deployed Lambda-context smoke write/read verification.

Defer: PDFs, presigned URLs, admin viewers, regeneration workflows, frontend work, Bedrock changes, SES changes, and broad IAM hardening beyond recording the follow-up.

## Sources

- `.planning/PROJECT.md` - active v1.2 target features and constraints.
- `.planning/milestones/s3-report-artifact-infrastructure.md` - slice scope, artifact contract, verification plan, and acceptance criteria.
- `src/stoa/config.py` - `s3_reports_bucket` backend setting.
- `src/stoa/services/report_service.py` - current artifact writes, metadata fields, JSON artifact shape, and private key builder.
- `src/stoa/db/repositories/report_repo.py` - report metadata access patterns.
- `src/stoa/routers/parents.py` - backend-mediated parent report access and ownership checks.
- `tests/test_report_service.py` - current unit coverage for S3 artifact write ordering and content types.
- `tests/test_report_flow.py` - current flow coverage for generation/storage/email ordering and S3 failure behavior.
