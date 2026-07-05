# v5.15 Research Summary: Usage, Quota, And Product Stability

## Stack Additions

No new runtime stack is required by default. Use existing FastAPI services, DynamoDB repositories, usage ledger service, account operations summaries, scripts, pytest, Ruff, and frontend build/e2e tooling.

## Feature Table Stakes

- Audit real usage-flow coverage before implementation.
- Lock idempotency and skip semantics for every governed usage action.
- Reconcile ledger, counters, entitlements, and support summaries.
- Provide support-safe quota explanations.
- Add core health/smoke checks for the flows most likely to break product operation.

## Watch Out For

- Duplicate/idempotent behavior must represent same intent, not just same payload.
- Support evidence must remain metadata-only.
- Health checks should separate service availability from product-flow readiness.
- v5.14 frontend e2e and external live-provider smoke remain separate blockers, not hidden v5.15 scope.

## Sources

- Stripe idempotent requests: https://docs.stripe.com/api/idempotent_requests
- AWS Builders' Library, retries and idempotent APIs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- OpenTelemetry HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- Kubernetes liveness/readiness probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
