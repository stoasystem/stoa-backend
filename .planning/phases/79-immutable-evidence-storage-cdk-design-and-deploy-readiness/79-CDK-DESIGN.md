# CDK Design: Immutable Evidence Storage

**Phase:** 79
**Status:** Complete

## Design Target

Create a CDK-managed immutable evidence storage path dedicated to metadata-only report operations retention manifests. The existing reports bucket remains private report artifact storage and must not be repurposed as a compliance-grade immutable evidence claim without explicit CDK evidence.

## Chosen CDK Path

Use a new dedicated S3 bucket in `StorageStack`, not the existing reports bucket:

- Stack file: `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`.
- Construct ID: `StoaImmutableEvidenceBucket`.
- Bucket name: `stoa-immutable-evidence-{account}`.
- Public access: `s3.BlockPublicAccess.BLOCK_ALL`.
- Encryption: `s3.BucketEncryption.S3_MANAGED`.
- SSL: `enforce_ssl=True`.
- Versioning: `versioned=True`.
- Object Lock: `object_lock_enabled=True`.
- Default Object Lock retention: `s3.ObjectLockRetention.governance(Duration.days(365))`.
- Access logs: existing `StoaLogsBucket`, prefix `immutable-evidence/`.
- Removal policy: `RemovalPolicy.RETAIN`.

`object_lock_enabled=True` must be present at bucket creation time. Phase 80 must create a new bucket rather than retrofitting Object Lock onto `stoa-reports-{account}`.

## API Stack Integration

Pass `immutable_evidence_bucket` from `StorageStack` into `ApiStack` in `/Users/zhdeng/stoa-infra/app.py`.

Inject these API Lambda environment variables:

- `IMMUTABLE_AUDIT_STORAGE_MODE=cdk_managed`
- `IMMUTABLE_AUDIT_STORAGE_CDK_MANAGED=true`
- `IMMUTABLE_AUDIT_STORAGE_RESOURCE=<immutable evidence bucket name>`
- `IMMUTABLE_AUDIT_STORAGE_PREFIX=audit-retention/`

Do not inject immutable storage settings into `stoa-weekly-report`; only `stoa-api` performs admin immutable manifest persistence.

## IAM Scope

Grant `stoa-api` only the object actions needed by the v2.7 writer for the immutable evidence prefix:

- `s3:PutObject`
- `s3:GetObject`

Resource scope:

- `immutable_evidence_bucket.arn_for_objects("audit-retention/*")`

Do not grant `s3:DeleteObject` on the immutable evidence bucket. Do not broaden existing `weekly-reports/*` report artifact permissions.

## Outputs

Phase 80 should add CloudFormation outputs on `StoaStorageStack`:

- `ImmutableEvidenceBucketName`
- `ImmutableEvidencePrefix`
- `ImmutableEvidenceObjectLockMode`
- `ImmutableEvidenceDefaultRetentionDays`

## Backend Object Boundary

Allowed immutable object content:

- Metadata-only retention manifest.
- Canonical digest and object byte digest metadata.
- Scope identifiers and redacted audit references.
- Retention policy ID, legal hold state, actor metadata, timestamps, and request IDs.

Forbidden content:

- Raw report artifacts.
- S3 keys or private bucket/key pairs for report artifacts.
- Presigned URLs.
- Raw report JSON or HTML.
- Auth tokens, cookies, passwords, AWS access keys, AWS secret keys, or session tokens.

## Open Design Questions

- Exact legal/compliance retention period remains future scope; v2.8 uses an operational default of 365 days in S3 Object Lock GOVERNANCE mode and must not claim broad regulatory compliance.
- Whether legal hold object-lock headers are needed per object remains future scope; v2.8 deploys default retention and preserves metadata-only legal hold state in DynamoDB.
- Production configured persistence verification should use a non-customer metadata-only safe fixture or release evidence bundle. It must not target customer reports.
