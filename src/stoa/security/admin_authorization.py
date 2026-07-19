"""Executable capability classification for every route registered below ``/admin``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Literal, ParamSpec, Protocol, TypeVar, runtime_checkable

from fastapi import Depends, HTTPException, Request

from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    ResourceRef,
    ResourceType,
    PolicyDecision,
    operator_capability_decision,
    record_authorization_decision,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id


async def _record_admin_decision(
    *,
    actor: Actor,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    decision: PolicyDecision,
    correlation_id: str,
    audit_sink: AuthorizationAuditSink,
    decision_kind: str,
) -> PolicyDecision:
    try:
        return await record_authorization_decision(
            actor=actor,
            resource=resource,
            action=action,
            purpose=purpose,
            decision=decision,
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind=decision_kind,
        )
    except SecurityDecisionError as error:
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": str(error.correlation_id)},
        ) from error


@dataclass(frozen=True, slots=True)
class AdminRoutePolicy:
    capability: str
    purpose: AuthorizationPurpose
    action: AuthorizationAction
    resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE
    target_keys: tuple[str, ...] = ()
    alternate_capabilities: tuple[str, ...] = ()

    @property
    def capabilities(self) -> tuple[str, ...]:
        return (self.capability, *self.alternate_capabilities)


AdminTargetCardinality = Literal["scalar", "collection", "resolver_collection", "reference_only"]


@dataclass(frozen=True, slots=True)
class AdminTargetProvider:
    """Executable, route-local handoff from a validated body to exact resources."""

    cardinality: AdminTargetCardinality
    body_parameter: str
    target_paths: tuple[str, ...]
    tuple_fields: tuple[str, ...]
    maximum: int | None = None
    required: bool = True
    reference_only: tuple[str, ...] = ()
    collection_path: str | None = None
    resolver: str | None = None


@dataclass(frozen=True, slots=True)
class AdminAuthorizationContext:
    request: Request
    policy: AdminRoutePolicy
    actor: Actor
    correlation_id: str
    audit_sink: AuthorizationAuditSink


@runtime_checkable
class _ModelDump(Protocol):
    def model_dump(self) -> dict[str, object]: ...


EndpointParams = ParamSpec("EndpointParams")
EndpointResult = TypeVar("EndpointResult")


class _ResolvedTargetNotFound(Exception):
    """Internal marker converted to the standard correlated 404 projection."""


def _read_typed_path(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _mapping_value(value: object, *, field: str) -> dict[str, object]:
    if isinstance(value, _ModelDump):
        return value.model_dump()
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {str(key): item for key, item in value.items()}
    if value is None:
        return {}
    raise ValueError(f"{field} must be an object")


def _positive_limit(value: object, *, default: int = 25) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("max_targets must be a positive integer")
    if isinstance(value, int):
        limit = value
    elif isinstance(value, str) and value.isdigit():
        limit = int(value)
    else:
        raise ValueError("max_targets must be a positive integer")
    if limit < 1:
        raise ValueError("max_targets must be a positive integer")
    return limit


def _string_sequence(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a string collection")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must contain only strings")
    return list(value)


def _canonical_coordinate(values: tuple[tuple[str, str], ...]) -> str:
    """Encode typed coordinates without delimiter ambiguity."""

    return "v1|" + "".join(
        f"{len(key)}:{key}{len(value)}:{value}" for key, value in values
    )


def _provider_refs(
    provider: AdminTargetProvider,
    body: object,
    request: Request,
    policy: AdminRoutePolicy,
    actor: Actor,
) -> tuple[ResourceRef, ...]:
    request_values = {**request.query_params, **request.path_params}
    if provider.resolver == "report_recovery_filters":
        from stoa.services import report_recovery_job_service

        filter_values = _mapping_value(
            _read_typed_path(body, "filters"), field="filters"
        )
        max_targets = _positive_limit(_read_typed_path(body, "max_targets"))
        job_type = (
            report_recovery_job_service.GENERATION_RETRY_JOB_TYPE
            if "retry-generation" in request.url.path
            else report_recovery_job_service.RESEND_JOB_TYPE
        )
        targets, _ = report_recovery_job_service._collect_targets(  # noqa: SLF001 - allowlisted read-only resolver
            job_type=job_type, filters=filter_values, max_targets=max_targets
        )
        # The resolver materializes identity only.  Preview-token/business-state
        # validation remains in the endpoint service after exact authorization.
        resolved_refs: list[ResourceRef] = []
        resolved_seen: set[str] = set()
        for target in targets:
            coordinates = tuple(
                (field, str(target[field]))
                for field in ("parent_id", "student_id", "week_start", "report_id")
                if target.get(field) not in (None, "")
            )
            if not coordinates:
                raise ValueError("resolved target is malformed")
            coordinate = _canonical_coordinate(coordinates)
            if coordinate in resolved_seen:
                raise ValueError("duplicate canonical target")
            resolved_seen.add(coordinate)
            resolved_refs.append(ResourceRef(
                policy.resource_type,
                coordinate,
                str(target.get("student_id") or target.get("parent_id") or actor.user_id),
                relationship_known=True,
            ))
        if not resolved_refs and provider.required:
            raise ValueError("resolved target collection is required")
        if not resolved_refs:
            resolved_refs.append(ResourceRef(policy.resource_type, "global", actor.user_id, relationship_known=True))
        return tuple(sorted(resolved_refs, key=lambda ref: (ref.resource_id, ref.student_id)))
    if provider.resolver == "report_recovery_resume":
        from stoa.db.repositories import report_repo
        from stoa.services import report_recovery_job_service

        job_id = str(request_values.get("job_id") or "")
        max_targets = _positive_limit(_read_typed_path(body, "max_targets"))
        results = _string_sequence(_read_typed_path(body, "results"), field="results")
        normalized = report_recovery_job_service._normalized_resume_results(results)  # noqa: SLF001
        source_job = report_repo.get_recovery_job(job_id)
        if not source_job:
            raise _ResolvedTargetNotFound
        # A non-terminal/type-invalid source is still an exact job target, but
        # its business-state rejection must happen only after authorization.
        if (
            str(source_job.get("job_type") or report_recovery_job_service.RESEND_JOB_TYPE)
            not in {
                report_recovery_job_service.RESEND_JOB_TYPE,
                report_recovery_job_service.GENERATION_RETRY_JOB_TYPE,
            }
            or source_job.get("status") not in report_recovery_job_service.RESUMABLE_SOURCE_STATUSES
        ):
            return (
                ResourceRef(
                    policy.resource_type,
                    _canonical_coordinate((("job_id", job_id),)),
                    actor.user_id,
                    relationship_known=True,
                ),
            )
        targets = report_recovery_job_service._collect_resume_targets(  # noqa: SLF001
            job_id, result_filters=normalized, max_targets=max_targets
        )
        resume_refs: list[ResourceRef] = []
        resume_seen: set[str] = set()
        for target in targets:
            coordinates = tuple(
                (field, str(target[field]))
                for field in ("parent_id", "student_id", "week_start", "report_id")
                if target.get(field) not in (None, "")
            )
            coordinate = _canonical_coordinate(coordinates)
            if not coordinates or coordinate in resume_seen:
                raise ValueError("malformed or duplicate resolved target")
            resume_seen.add(coordinate)
            resume_refs.append(ResourceRef(
                policy.resource_type, coordinate,
                str(target.get("student_id") or target.get("parent_id") or actor.user_id),
                relationship_known=True,
            ))
        if not resume_refs and provider.required:
            raise ValueError("resolved target collection is required")
        if not resume_refs:
            resume_refs.append(ResourceRef(policy.resource_type, "global", actor.user_id, relationship_known=True))
        return tuple(sorted(resume_refs, key=lambda ref: (ref.resource_id, ref.student_id)))
    if provider.resolver == "support_handoff":
        from stoa.db.repositories import report_repo

        coordinate_maps: list[dict[str, str]] = []
        destination = str(_read_typed_path(body, "destination_mode") or "preview").strip()
        consumes_recovery_evidence = destination in {
            "preview", "copy", "download", "internal_queue", "third_party_support",
        }
        for job_id in _string_sequence(
            _read_typed_path(body, "recovery_job_ids"), field="recovery_job_ids"
        ):
            if not consumes_recovery_evidence:
                coordinate_maps.append({"job_id": str(job_id)})
                continue
            job = report_repo.get_recovery_job(str(job_id))
            if not job:
                raise _ResolvedTargetNotFound
            filters = job.get("filters") or {}
            coordinate_maps.append({
                key: str(value) for key, value in {
                    "job_id": job_id,
                    "parent_id": filters.get("parent_id"),
                    "student_id": filters.get("student_id"),
                }.items() if value not in (None, "")
            })
        fixture = _read_typed_path(body, "fixture")
        if fixture is not None:
            fixture_values = {
                key: str(_read_typed_path(fixture, key))
                for key in ("parent_id", "student_id", "week_start")
                if _read_typed_path(fixture, key) not in (None, "")
            }
            if fixture_values:
                coordinate_maps.append(fixture_values)
        handoff_refs: list[ResourceRef] = []
        handoff_seen: set[str] = set()
        for values in coordinate_maps:
            coordinates = tuple((key, values[key]) for key in ("job_id", "parent_id", "student_id", "week_start") if key in values)
            coordinate = _canonical_coordinate(coordinates)
            if coordinate in handoff_seen:
                raise ValueError("duplicate canonical target")
            handoff_seen.add(coordinate)
            handoff_refs.append(ResourceRef(
                policy.resource_type, coordinate,
                values.get("student_id") or values.get("parent_id") or actor.user_id,
                relationship_known=True,
            ))
        if not handoff_refs:
            handoff_refs.append(ResourceRef(policy.resource_type, "global", actor.user_id, relationship_known=True))
        return tuple(sorted(handoff_refs, key=lambda ref: (ref.resource_id, ref.student_id)))
    items: list[object]
    if provider.collection_path:
        raw = _read_typed_path(body, provider.collection_path)
        items = list(raw or ()) if isinstance(raw, (list, tuple)) else []
    else:
        items = [body]
    if provider.maximum is not None and len(items) > provider.maximum:
        raise ValueError("target collection exceeds declared maximum")
    if provider.required and not items:
        raise ValueError("target collection is required")

    provider_refs: list[ResourceRef] = []
    provider_seen: set[str] = set()
    for item in items:
        provider_coordinates: list[tuple[str, str]] = []
        for field in provider.tuple_fields:
            body_path = field
            if provider.collection_path and body_path.startswith(provider.collection_path + "."):
                body_path = body_path[len(provider.collection_path) + 1 :]
            body_value = _read_typed_path(item, body_path)
            request_value = request_values.get(field)
            if body_value not in (None, "") and request_value not in (None, "") and str(body_value) != str(request_value):
                raise ValueError("conflicting target coordinates")
            selected = body_value if body_value not in (None, "") else request_value
            if selected not in (None, ""):
                provider_coordinates.append((field, str(selected)))
        # Path/query coordinates enrich the same scalar tuple.
        if provider.cardinality == "scalar":
            present = {key for key, _ in provider_coordinates}
            for field in policy.target_keys:
                selected = request_values.get(field)
                if selected not in (None, "") and field not in present:
                    provider_coordinates.append((field, str(selected)))
        if not provider_coordinates:
            if provider.required:
                raise ValueError("target coordinate is required")
            continue
        coordinate = _canonical_coordinate(tuple(provider_coordinates))
        if coordinate in provider_seen:
            raise ValueError("duplicate canonical target")
        provider_seen.add(coordinate)
        leaf_values = {
            key.rsplit(".", 1)[-1]: value for key, value in provider_coordinates
        }
        student_id = str(
            leaf_values.get("student_id")
            or leaf_values.get("user_id")
            or leaf_values.get("parent_id")
            or actor.user_id
        )
        provider_refs.append(ResourceRef(policy.resource_type, coordinate, student_id, relationship_known=True))
    if not provider_refs and not provider.required:
        provider_refs.append(ResourceRef(policy.resource_type, "global", actor.user_id, relationship_known=True))
    return tuple(sorted(provider_refs, key=lambda ref: (ref.resource_id, ref.student_id)))


def _exception_status(error: Exception) -> int:
    value = getattr(error, "status_code", 500)
    return value if isinstance(value, int) and not isinstance(value, bool) else 500


def admin_target_provider(
    provider: AdminTargetProvider,
) -> Callable[
    [Callable[EndpointParams, Awaitable[EndpointResult]]],
    Callable[EndpointParams, Awaitable[EndpointResult]],
]:
    """Wrap a registered endpoint so validated typed targets are authorized first."""

    def decorate(
        endpoint: Callable[EndpointParams, Awaitable[EndpointResult]],
    ) -> Callable[EndpointParams, Awaitable[EndpointResult]]:
        @wraps(endpoint)
        async def wrapped(
            *args: EndpointParams.args, **kwargs: EndpointParams.kwargs
        ) -> EndpointResult:
            user = kwargs.get("user")
            if not isinstance(user, dict) or "_admin_authorization" not in user:
                raise RuntimeError("typed admin target provider lacks authorization context")
            context = user["_admin_authorization"]
            if not isinstance(context, AdminAuthorizationContext):
                raise RuntimeError("typed admin target provider has invalid authorization context")
            body = kwargs.get(provider.body_parameter)
            try:
                refs = _provider_refs(
                    provider,
                    body,
                    context.request,
                    context.policy,
                    context.actor,
                )
            except HTTPException:
                raise
            except _ResolvedTargetNotFound as exc:
                raise _admin_http_error(
                        SecurityDecisionError(
                            SecurityErrorCode.RESOURCE_NOT_FOUND,
                            context.correlation_id,
                    )
                ) from exc
            except (TypeError, ValueError) as exc:
                error = SecurityDecisionError(
                    SecurityErrorCode.ACTION_NOT_ALLOWED,
                    context.correlation_id,
                    internal_detail=type(exc).__name__,
                )
                raise _admin_http_error(error) from exc
            except Exception as exc:
                status_code = _exception_status(exc)
                if status_code == 422:
                    detail = getattr(exc, "detail", "Invalid recovery target selection")
                    raise HTTPException(
                        status_code=422,
                        detail=str(detail),
                    ) from exc
                code = (
                    SecurityErrorCode.ACTION_NOT_ALLOWED
                    if 400 <= status_code < 500
                    else SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
                )
                error = SecurityDecisionError(
                    code,
                    context.correlation_id,
                    internal_detail=type(exc).__name__,
                )
                raise _admin_http_error(error) from exc
            await _authorize_admin_refs(
                refs=refs,
                request=context.request,
                policy=context.policy,
                actor=context.actor,
                correlation_id=context.correlation_id,
                audit_sink=context.audit_sink,
            )
            return await endpoint(*args, **kwargs)

        setattr(wrapped, "admin_target_provider", provider)
        return wrapped

    return decorate


def _policy(capability: str, purpose: AuthorizationPurpose, action: AuthorizationAction, *targets: str,
            resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE,
            alternate_capabilities: tuple[str, ...] = ()) -> AdminRoutePolicy:
    return AdminRoutePolicy(capability, purpose, action, resource_type, targets, alternate_capabilities)


def classify_admin_route(method: str, path: str) -> AdminRoutePolicy:
    """Return one exact executable policy for an admin-prefixed registered route."""
    method = method.upper()
    action = {
        "GET": AuthorizationAction.READ,
        "PATCH": AuthorizationAction.UPDATE,
        "DELETE": AuthorizationAction.DELETE,
    }.get(method, AuthorizationAction.CREATE)

    if path == "/admin/notifications":
        return _policy("notification_event_inspector", AuthorizationPurpose.NOTIFICATION_EVENT_INSPECTION,
                       AuthorizationAction.READ, resource_type=ResourceType.NOTIFICATION_EVENT)
    if path == "/admin/notifications/delivery-status":
        return _policy("notification_delivery_health_reader", AuthorizationPurpose.NOTIFICATION_DELIVERY_HEALTH,
                       AuthorizationAction.READ, resource_type=ResourceType.NOTIFICATION_COLLECTION)
    if path.startswith("/admin/privileged-identities"):
        return _policy("admin_identity_manager", AuthorizationPurpose.IDENTITY_MANAGEMENT,
                       AuthorizationAction.MANAGE_PRIVILEGE, "target_id")
    if path.startswith("/admin/moderation"):
        return _policy("student_safety_review", AuthorizationPurpose.MODERATION_OPERATIONS, action, "case_id")
    if path.startswith("/admin/curriculum"):
        alternates: tuple[str, ...] = ()
        if "/analytics/" in path:
            capability = "curriculum_analytics_reader" if "warehouse-export" not in path else "curriculum_analytics_exporter"
            op_action = AuthorizationAction.EXPORT if "warehouse-export" in path else AuthorizationAction.READ
        elif "/migrations/" in path:
            capability = "migration_operator"
            op_action = action
            alternates = ("curriculum_publisher",)
        elif "validation-preview" in path or path.endswith("/preview"):
            capability = "curriculum_author"
            op_action = AuthorizationAction.READ
            alternates = ("curriculum_reviewer", "curriculum_publisher")
        elif "diff" in path or "audit" in path or "worklist" in path or method == "GET":
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.READ
            alternates = ("curriculum_publisher",)
        elif "/submit-review" in path:
            capability = "curriculum_author"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        elif any(marker in path for marker in ("/approve", "/request-changes", "/submit-review")):
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ("curriculum_publisher",)
        elif any(marker in path for marker in ("/publish", "/rollback", "/archive")):
            capability = "curriculum_publisher"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        else:
            capability = "curriculum_author"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        return _policy(capability, AuthorizationPurpose.CURRICULUM_OPERATIONS, op_action,
                       "public_lesson_id", "version_id", "migration_id",
                       alternate_capabilities=alternates)
    if path.startswith("/admin/users"):
        capability = "admin_identity_manager" if method != "GET" else "student_support_lookup"
        op_action = AuthorizationAction.MANAGE_PRIVILEGE if method != "GET" else AuthorizationAction.LOOKUP
        return _policy(capability, AuthorizationPurpose.ACCOUNT_OPERATIONS, op_action, "user_id")
    if path.startswith("/admin/account-verification") or path.startswith("/admin/account-operations"):
        return _policy("student_support_lookup", AuthorizationPurpose.ACCOUNT_OPERATIONS,
                       AuthorizationAction.LOOKUP, "user_id", "parent_id")
    if path.startswith("/admin/parent-bindings"):
        capability = "parent_binding_repairer" if method != "GET" else "student_support_lookup"
        return _policy(capability, AuthorizationPurpose.ACCOUNT_OPERATIONS,
                       AuthorizationAction.UPDATE if method != "GET" else AuthorizationAction.LOOKUP,
                       "parent_id", "student_id", resource_type=ResourceType.PARENT_BINDING)
    if path.startswith("/admin/subscriptions"):
        if "/refunds" in path:
            capability, op_action = "billing_refund_executor", AuthorizationAction.UPDATE
        elif "accounting-export" in path:
            capability, op_action = "billing_accounting_exporter", AuthorizationAction.EXPORT
        elif "rollout-controls" in path and method != "GET":
            capability, op_action = "billing_rollout_manager", AuthorizationAction.UPDATE
        elif method == "GET":
            capability, op_action = "billing_operations_reader", AuthorizationAction.READ
        else:
            capability, op_action = "billing_operations_manager", action
        return _policy(capability, AuthorizationPurpose.BILLING_OPERATIONS, op_action,
                       "parent_id", "request_id")
    if path.startswith("/admin/usage"):
        capability = "usage_reconciliation_operator" if "reconciliation" in path else "usage_event_inspector"
        op_action = AuthorizationAction.UPDATE if "reconciliation" in path else AuthorizationAction.READ
        return _policy(capability, AuthorizationPurpose.USAGE_OPERATIONS, op_action, "student_id")
    if path.startswith("/admin/reports"):
        targets = ("parent_id", "student_id", "week_start", "job_id", "delivery_id", "report_id")
        if any(marker in path for marker in ("support-handoff-delivery", "/messages", "/provider-sync", "/retry")):
            capability = "report_external_handoff_sender" if method != "GET" else "report_handoff_reader"
            op_action = AuthorizationAction.EXTERNAL_SEND if method != "GET" else AuthorizationAction.READ
            purpose = AuthorizationPurpose.SUPPORT_HANDOFF
        elif any(marker in path for marker in ("audit-retention", "immutable-evidence", "retention-governance", "legal-holds")):
            capability = "report_governance_reader" if (method == "GET" or path.endswith("/status")) else "report_governance_manager"
            op_action = AuthorizationAction.READ if capability.endswith("reader") else AuthorizationAction.UPDATE
            purpose = AuthorizationPurpose.AUDIT_GOVERNANCE
        elif any(marker in path for marker in ("recovery-evidence", "support-package", "support-handoff-package", "release-evidence")):
            capability = "report_evidence_exporter"
            op_action = AuthorizationAction.EXPORT
            purpose = AuthorizationPurpose.REPORT_RECOVERY
        elif any(marker in path for marker in ("resend", "retry-generation", "recovery-jobs", "edit-drafts", "artifact-edit", "artifact-rollback")):
            capability = "report_recovery_reader" if method == "GET" else "report_recovery_operator"
            op_action = AuthorizationAction.READ if method == "GET" else AuthorizationAction.UPDATE
            purpose = AuthorizationPurpose.REPORT_RECOVERY
        else:
            capability = "report_metadata_reader"
            op_action = AuthorizationAction.READ
            purpose = AuthorizationPurpose.REPORT_OPERATIONS
        return _policy(capability, purpose, op_action, *targets, resource_type=ResourceType.REPORT)
    if path.startswith("/admin/bi"):
        capability = "bi_exporter" if "warehouse-export" in path else "bi_operations_reader"
        return _policy(capability, AuthorizationPurpose.GLOBAL_OPERATIONS,
                       AuthorizationAction.EXPORT if "warehouse-export" in path else AuthorizationAction.READ)
    if path.startswith("/admin/external-activation"):
        return _policy("production_readiness_reader", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    if path.startswith("/admin/teacher-dispatch"):
        return _policy("teacher_dispatch_operator", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    if path in {"/admin/stats", "/admin/core-smoke"}:
        return _policy("platform_operations_reader", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    raise KeyError(f"unclassified admin route: {method} {path}")


async def _target(
    request: Request,
    policy: AdminRoutePolicy,
    actor: Actor,
    correlation_id: str,
) -> tuple[str, str]:
    values = {**request.query_params, **request.path_params}
    try:
        if values.get("job_id"):
            from stoa.db.repositories import report_repo

            job = report_repo.get_recovery_job(str(values["job_id"]))
            if not job:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
                raise HTTPException(
                    error.status_code,
                    detail=error.public_body(),
                    headers={"X-Correlation-ID": correlation_id},
                )
            filters = job.get("filters") or {}
            values.setdefault("student_id", filters.get("student_id"))
            values.setdefault("parent_id", filters.get("parent_id"))
        if values.get("delivery_id"):
            from stoa.db.repositories import report_repo

            delivery = report_repo.get_support_handoff_delivery_record(
                str(values["delivery_id"])
            )
            if not delivery:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
                raise HTTPException(
                    error.status_code,
                    detail=error.public_body(),
                    headers={"X-Correlation-ID": correlation_id},
                )
            values.setdefault("student_id", delivery.get("student_id"))
            values.setdefault("parent_id", delivery.get("parent_id"))
    except HTTPException:
        raise
    except Exception as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            correlation_id,
            internal_detail=type(exc).__name__,
        )
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from exc
    selected = [(key, str(values[key])) for key in policy.target_keys if values.get(key)]
    if not selected:
        return "global", actor.user_id
    resource_id = ":".join(value for _, value in selected)
    student_id = str(values.get("student_id") or values.get("user_id") or values.get("parent_id") or actor.user_id)
    return resource_id, student_id


def _admin_http_error(error: SecurityDecisionError) -> HTTPException:
    return HTTPException(
        error.status_code,
        detail=error.public_body(),
        headers={"X-Correlation-ID": str(error.correlation_id)},
    )


async def _authorize_admin_refs(
    *,
    refs: tuple[ResourceRef, ...],
    request: Request,
    policy: AdminRoutePolicy,
    actor: Actor,
    correlation_id: str,
    audit_sink: AuthorizationAuditSink,
) -> None:
    if not refs:
        raise _admin_http_error(
            SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, correlation_id)
        )
    # All decisions are computed first.  No allow evidence can turn a later deny
    # into a partially released command.
    decisions: list[tuple[ResourceRef, PolicyDecision]] = []
    for ref in refs:
        candidates = [
            operator_capability_decision(
                actor,
                capability=capability,
                resource=ref,
                action=policy.action,
                purpose=policy.purpose,
            )
            for capability in policy.capabilities
            if any(grant.capability == capability for grant in actor.current_grants)
        ]
        decision = next((item for item in candidates if item.allowed), candidates[0])
        decisions.append((ref, decision))
    denied = next(((ref, decision) for ref, decision in decisions if not decision.allowed), None)
    if denied is not None:
        ref, decision = denied
        decision = await _record_admin_decision(
            actor=actor,
            resource=ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=decision,
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_target",
        )
        raise _admin_http_error(SecurityDecisionError(decision.result_code, correlation_id))
    # Mandatory per-target durable evidence completes before the endpoint body.
    for ref, decision in decisions:
        await _record_admin_decision(
            actor=actor,
            resource=ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=decision,
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_capability",
        )


async def admin_operation(
    request: Request,
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> dict[str, object]:
    route = request.scope.get("route")
    path = str(getattr(route, "path", request.url.path))
    try:
        policy = classify_admin_route(request.method, path)
    except KeyError as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.ACTION_NOT_ALLOWED,
            correlation_id,
            internal_detail=str(exc),
        )
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from exc
    provisional_ref = ResourceRef(
        policy.resource_type,
        path,
        actor.user_id,
        relationship_known=True,
    )
    eligible_role = actor.role.value == "admin" or (
        actor.role.value == "teacher"
        and any(
            capability.startswith("curriculum_") or capability == "migration_operator"
            for capability in policy.capabilities
        )
    )
    if (
        not actor.can_authorize
        or not eligible_role
        or not any(grant.capability in policy.capabilities for grant in actor.current_grants)
    ):
        decision = await _record_admin_decision(
            actor=actor,
            resource=provisional_ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=PolicyDecision(False, SecurityErrorCode.ACTION_NOT_ALLOWED),
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_precheck",
        )
        error = SecurityDecisionError(decision.result_code, correlation_id)
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from error
    provider = getattr(getattr(route, "endpoint", None), "admin_target_provider", None)
    if provider is not None:
        return {
            "sub": actor.user_id,
            "user_id": actor.user_id,
            "role": actor.role.value,
            "account_status": actor.account_status.value,
            "capabilities": {grant.capability: "granted" for grant in actor.current_grants},
            "_admin_authorization": AdminAuthorizationContext(
                request=request,
                policy=policy,
                actor=actor,
                correlation_id=correlation_id,
                audit_sink=audit_sink,
            ),
        }
    try:
        resource_id, student_id = await _target(request, policy, actor, correlation_id)
    except HTTPException as exc:
        await _record_admin_decision(
            actor=actor,
            resource=provisional_ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=PolicyDecision(False, SecurityErrorCode.RESOURCE_NOT_FOUND),
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_target",
        )
        raise exc
    ref = ResourceRef(policy.resource_type, resource_id, student_id, relationship_known=True)
    selected_capability = next(
        capability
        for capability in policy.capabilities
        if any(grant.capability == capability for grant in actor.current_grants)
    )
    decision = operator_capability_decision(
        actor,
        capability=selected_capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    )
    decision = await _record_admin_decision(
        actor=actor,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
        decision=decision,
        correlation_id=correlation_id,
        audit_sink=audit_sink,
        decision_kind="admin_capability",
    )
    if not decision.allowed:
        error = SecurityDecisionError(decision.result_code, correlation_id)
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from error
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "account_status": actor.account_status.value,
        "capabilities": {
            grant.capability: "granted" for grant in actor.current_grants
        },
    }


setattr(admin_operation, "admin_policy_classifier", classify_admin_route)
