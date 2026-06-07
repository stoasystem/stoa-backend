# CDK Design: Immutable Evidence Storage

**Phase:** 79
**Status:** Planned

## Design Target

Create a CDK-managed immutable evidence storage path dedicated to metadata-only report operations retention manifests. The existing reports bucket remains private report artifact storage and must not be repurposed as a compliance-grade immutable evidence claim without explicit CDK evidence.

## Resource Contract

The CDK design must define:

- Dedicated immutable evidence storage resource or explicitly approved immutable evidence prefix/resource boundary.
- Encryption posture.
- Retention/object-lock posture and any constraints discovered during CDK/AWS review.
- Removal policy and teardown expectations.
- API Lambda environment variables for resource name, prefix, mode/status, and verification settings.
- API Lambda IAM permissions scoped to immutable evidence writes/reads only.
- CloudFormation outputs or deploy evidence needed for release gate.

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

- Whether immutable storage must be a new resource created with immutable/object-lock settings from inception.
- Exact retention period and mode pending compliance/legal approval.
- Whether Phase 80 should deploy storage disabled-by-default before Phase 81 enables backend writes.
- Whether separate production smoke fixture metadata is required for first configured persistence verification.
