# Phase 476: User Setup Required

**Generated:** 2026-07-24
**Phase:** 476-billing-idempotency-and-paid-access-recovery
**Status:** Incomplete

The Plan 04 implementation and local dry-run evidence are complete. A real
non-production inventory preview remains intentionally unexecuted until an
approved operator supplies the environment and read-only sandbox authority.

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `STOA_BILLING_MIGRATION_ENVIRONMENT` | Approved non-production environment identifier; `production`, `prod`, and `live` are rejected | Operator shell/session |
| [ ] | `STRIPE_SECRET_KEY` | Stripe Dashboard → Developers → API keys → restricted sandbox/test read key; must begin with `sk_test_` | Approved secret store/operator session |

## Access Approval

- [ ] Approve read-only access to the exact non-production DynamoDB billing/profile inventory.
- [ ] Approve read-only access to the matching Stripe sandbox subscriptions and Prices.
- [ ] Review every `migration_review_required` row and supply an evidence-bound disposition before any apply attempt.

## Verification

After approved access is available, create an exact bounded coordinate input
and run preview only. Do not run apply against production or live-mode evidence.

```bash
PYTHONPATH=. .venv/bin/python -m stoa.jobs.migrate_billing_plan_identity preview \
  --environment "$STOA_BILLING_MIGRATION_ENVIRONMENT" \
  --input "$STOA_BILLING_MIGRATION_INPUT" \
  --output docs/security/phase-476-plan-migration-preview.json

PYTHONPATH=. .venv/bin/python -m stoa.jobs.migrate_billing_plan_identity verify-preview \
  --results docs/security/phase-476-plan-migration-preview.json
```

Expected results:

- Preview reports `mutationCount: 0`.
- Every unresolved legacy plan or trial row remains `migration_review_required`.
- Receipt contains only source/configuration/row/evidence digests and safe classifications.
- Apply remains blocked until all review rows have matching evidence-bound dispositions.

---

**Once all items complete:** Mark status as "Complete" at top of file.
