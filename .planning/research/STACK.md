# v5.15 Research: Stack

## Scope

Usage, quota, reconciliation, and product stability for the existing STOA backend/frontend. This milestone should reuse the current FastAPI, DynamoDB, Cognito, Lambda/API Gateway, and React/Playwright stack.

## Findings

- Idempotency should continue to use caller/request identifiers rather than deriving duplicate intent only from payload equality. AWS's Builders' Library recommends caller-provided request identifiers because identical payloads can still represent different business intent.
- Usage writes should follow Stripe-like idempotency properties where the same idempotency key returns a semantically equivalent result and mismatched parameters are rejected or flagged.
- Observability should use low-cardinality error/status codes. OpenTelemetry's HTTP semantic conventions emphasize predictable `error.type` values and standard HTTP metadata rather than high-cardinality private payloads.
- Health checks should distinguish readiness from liveness. Kubernetes docs treat readiness as traffic eligibility and liveness as restart/remediation eligibility; STOA can mirror that distinction with smoke scripts and health metadata even if Lambda/API Gateway is not Kubernetes-hosted.

## Implications For STOA

- No new infrastructure is required for v5.15 by default.
- DynamoDB ledger/counter reconciliation can be implemented in existing repositories/services.
- Smoke checks should be scripts or admin-only endpoints that return request IDs, route names, status codes, and support-safe blockers.
- Avoid storing raw question/chat/learning content in usage evidence.

## Sources

- Stripe idempotent requests: https://docs.stripe.com/api/idempotent_requests
- AWS Builders' Library, retries and idempotent APIs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- OpenTelemetry HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- Kubernetes liveness/readiness probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
