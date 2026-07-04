# Phase 236 Release Gate

## Decision

Pass for local/internal readiness.

## Release State

`curriculum-buildout-ready`

## Backend Evidence

- `tests/test_curriculum_ops.py`, `tests/test_curriculum_migration.py`, and `tests/test_curriculum_rollout.py`: 23 passed.
- `tests/test_curriculum_analytics.py`: 12 passed.
- Targeted Ruff: passed.

## Frontend Evidence

- `npm run build`: passed.
- `npm run lint`: passed.
- `admin-curriculum.spec.ts`: 4 passed.

## Authorization Matrix

| Operation | Required backend capability |
|-----------|-----------------------------|
| Draft create/patch | `curriculum_author` |
| Validation preview | `curriculum_author` |
| Diff/audit review | `curriculum_reviewer` or publisher-level capability |
| Review approve/request changes | `curriculum_reviewer` |
| Publish/rollback/archive | `curriculum_publisher` |
| Migration dry-run/apply/evidence | `migration_operator` or publisher-level capability |

Ordinary teacher/tutor roles are refused unless the backend grants one of these explicit curriculum capabilities.

## Deferred Items

- Real approved production content source import.
- Production deploy/live smoke.
- Live warehouse/BI.
- Broad collaborative CMS features.
- Unreviewed AI publication.
