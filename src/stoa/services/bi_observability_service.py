"""Support-safe BI observability and product analytics contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Callable

from stoa.config import Settings
from stoa.services import (
    core_smoke_service,
    curriculum_analytics_service,
    external_activation_service,
    notification_service,
    subscription_service,
    support_sla_service,
    usage_ledger_service,
)


SCHEMA_VERSION = "stoa.bi_observability.v1"
TAXONOMY = [
    "live_ready",
    "read_only_verifiable",
    "safe_fixture_verifiable",
    "locally_ready",
    "blocked",
    "failed",
    "unknown",
]
FORBIDDEN_FIELDS = [
    "answer",
    "auth_token",
    "chat_message",
    "cognito_token",
    "correct_answer",
    "login_code",
    "private_s3_key",
    "prompt",
    "provider_payload",
    "report_artifact_content",
    "secret",
    "student_answer",
    "verification_code",
]


def build_taxonomy_contract() -> dict[str, Any]:
    """Return the shared BI status taxonomy and privacy contract."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "taxonomy": list(TAXONOMY),
        "states": {
            "live_ready": "Live provider or product signal is configured, approved, and enabled.",
            "read_only_verifiable": "Signal can be inspected without customer-impacting mutation.",
            "safe_fixture_verifiable": "Signal can be verified only with an approved safe fixture.",
            "locally_ready": "Local implementation is ready, but live provider evidence is absent.",
            "blocked": "Required credentials, approval, fixture, or provider state is missing.",
            "failed": "A product regression or provider call failure is present.",
            "unknown": "The source could not be inspected in the current environment.",
        },
        "privacy": _privacy_contract(),
    }


def build_warehouse_readiness(settings: Settings) -> dict[str, Any]:
    """Build a bounded readiness report for aggregate BI export activation."""
    generated_at = _now_iso()
    curriculum = _safe_source("curriculum_analytics", curriculum_analytics_service.warehouse_readiness)
    payment_auth = _safe_source(
        "payment_auth_activation",
        lambda: external_activation_service.build_payment_auth_smoke_report(settings),
    )
    notification_support = _safe_source(
        "notification_support_activation",
        lambda: external_activation_service.build_notification_support_smoke_report(settings),
    )
    production = _safe_source(
        "production_readiness",
        lambda: external_activation_service.build_production_readiness_smoke_report(settings),
    )
    core = _safe_source("core_smoke", core_smoke_service.build_core_smoke_report)

    sources = [
        _readiness_source(
            "curriculum_analytics",
            "GET /admin/curriculum/analytics/warehouse-export",
            _classify_curriculum_readiness(curriculum),
            curriculum,
        ),
        _readiness_source(
            "payment_auth_activation",
            "GET /admin/external-activation/payment-auth-smoke",
            _source_state(payment_auth, "overallState"),
            payment_auth,
        ),
        _readiness_source(
            "notification_support_activation",
            "GET /admin/external-activation/notification-support-smoke",
            _source_state(notification_support, "overallState"),
            notification_support,
        ),
        _readiness_source(
            "production_readiness",
            "GET /admin/external-activation/production-readiness-smoke",
            _source_state(production, "overallState"),
            production,
        ),
        _readiness_source(
            "core_smoke",
            "GET /admin/core-smoke",
            _classify_core_smoke(core),
            core,
        ),
    ]
    blockers = _unique(
        [
            *_collect_blockers(curriculum),
            *_collect_blockers(payment_auth),
            *_collect_blockers(notification_support),
            *_collect_blockers(production),
        ]
    )
    if not settings.bi_warehouse_live_configured:
        blockers.append("live_bi_warehouse_not_configured")
    if not settings.bi_warehouse_export_enabled:
        blockers.append("bi_warehouse_export_not_enabled")

    return {
        "generatedAt": generated_at,
        "schemaVersion": SCHEMA_VERSION,
        "taxonomy": list(TAXONOMY),
        "overallState": "live_ready" if settings.bi_warehouse_live_configured and settings.bi_warehouse_export_enabled and not blockers else "blocked",
        "exportAllowed": bool(settings.bi_warehouse_export_enabled and not blockers),
        "liveWarehouseConfigured": bool(settings.bi_warehouse_live_configured),
        "sources": sources,
        "blockers": _unique(blockers),
        "warnings": _unique([*_collect_warnings(curriculum), *_collect_warnings(payment_auth), *_collect_warnings(notification_support)]),
        "privacy": _privacy_contract(),
        "operations": {
            "bounded": True,
            "idempotency": "stable_period_schema_and_filter_key",
            "backfill": "manual_period_parameter",
            "retry": "rerun_same_period_and_filters",
            "partialFailure": "source_state_marks_partial_or_unknown",
            "staleDataPolicy": "source_stale_flag_and_generatedAt_required",
        },
    }


def build_warehouse_export(
    *,
    settings: Settings,
    period: str = "latest",
    limit: int = 100,
) -> dict[str, Any]:
    """Build aggregate warehouse rows across product/provider readiness surfaces."""
    bounded_limit = max(1, min(limit, 250))
    generated_at = _now_iso()
    sources = _export_sources(settings=settings, period=period, limit=bounded_limit)
    rows: list[dict[str, Any]] = []
    for source in sources:
        rows.extend(source["rows"])
    rows = rows[:bounded_limit]
    export_key = _stable_key("warehouse-export", period, str(bounded_limit), SCHEMA_VERSION)
    return {
        "generatedAt": generated_at,
        "schemaVersion": SCHEMA_VERSION,
        "exportId": export_key,
        "idempotencyKey": export_key,
        "period": period,
        "count": len(rows),
        "bounded": True,
        "limit": bounded_limit,
        "rows": rows,
        "sources": [
            {
                "name": source["name"],
                "state": source["state"],
                "rowCount": len(source["rows"]),
                "partial": source["partial"],
                "stale": source["stale"],
                "blockers": source["blockers"],
            }
            for source in sources
        ],
        "privacy": _privacy_contract(),
        "operations": {
            "backfill": {"supported": True, "mode": "rerun_with_period", "customerMutationAllowed": False},
            "retry": {"supported": True, "idempotencyKey": export_key},
            "partialFailure": {"representedBy": "sources[].partial and source state unknown_or_failed"},
            "staleData": {"representedBy": "sources[].stale and generatedAt"},
        },
    }


def build_operator_dashboard(
    *,
    settings: Settings,
    limit: int = 100,
) -> dict[str, Any]:
    """Return aggregate operator dashboard sections without raw content."""
    generated_at = _now_iso()
    readiness = build_warehouse_readiness(settings)
    export = build_warehouse_export(settings=settings, period="latest", limit=limit)
    core = _safe_source("core_smoke", core_smoke_service.build_core_smoke_report)
    curriculum = _safe_source(
        "curriculum_dashboard",
        lambda: curriculum_analytics_service.operator_dashboard(limit=limit),
    )
    notification = _safe_source("notification_delivery", lambda: notification_service.delivery_status(limit=limit))
    support = _safe_source(
        "support_sla",
        lambda: support_sla_service.build_support_sla_analytics(settings=settings, limit=limit),
    )
    payment = _safe_source("payment_provider_readiness", lambda: subscription_service.get_provider_readiness(settings))

    sections = [
        _dashboard_section(
            "usage_quota",
            "locally_ready",
            {
                "ledgerActions": len(usage_ledger_service.USAGE_ACTION_DEFINITIONS),
                "summaryGroups": sorted(
                    {
                        action.summary_group
                        for action in usage_ledger_service.USAGE_ACTION_DEFINITIONS.values()
                    }
                ),
            },
            blockers=[],
            support_actions=["use_admin_usage_summary_or_reconciliation_for_student_specific_debug"],
        ),
        _dashboard_section("billing_provider", _classify_payment(payment), _billing_summary(payment), blockers=_collect_blockers(payment)),
        _dashboard_section("curriculum_analytics", _classify_curriculum_dashboard(curriculum), _curriculum_summary(curriculum), blockers=_collect_blockers(curriculum)),
        _dashboard_section("teacher_help_support", _classify_support(support), _support_summary(support), blockers=_collect_blockers(support)),
        _dashboard_section("notification_delivery", _classify_notification(notification), _notification_summary(notification), blockers=_collect_blockers(notification)),
        _dashboard_section("release_smoke", _classify_core_smoke(core), core.get("summary", {}), blockers=_collect_blockers(core)),
        _dashboard_section("warehouse_export", readiness["overallState"], {"latestRowCount": export["count"]}, blockers=readiness["blockers"]),
    ]

    blocker_counts: dict[str, int] = {}
    for section in sections:
        for blocker in section["blockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    return {
        "generatedAt": generated_at,
        "schemaVersion": SCHEMA_VERSION,
        "taxonomy": list(TAXONOMY),
        "sections": sections,
        "summary": {
            "sectionCount": len(sections),
            "blockedSections": sum(1 for section in sections if section["state"] == "blocked"),
            "failedSections": sum(1 for section in sections if section["state"] == "failed"),
            "partialSections": sum(1 for section in sections if section["partial"]),
            "staleSections": sum(1 for section in sections if section["stale"]),
            "blockerCounts": blocker_counts,
        },
        "emptyState": None if any(section["aggregate"] for section in sections) else "No aggregate observability data is available yet.",
        "privacy": _privacy_contract(),
    }


def build_alert_routing(settings: Settings) -> dict[str, Any]:
    """Return low-cardinality alert routing metadata and runbook hooks."""
    dashboard = build_operator_dashboard(settings=settings)
    routes: list[dict[str, Any]] = []
    for section in dashboard["sections"]:
        state = section["state"]
        if state == "failed":
            alert_class = "product_regression"
            severity = "sev2"
        elif state == "blocked" and section["name"] in {"billing_provider", "notification_delivery", "teacher_help_support", "warehouse_export"}:
            alert_class = "provider_blocker"
            severity = "sev3"
        elif state in {"read_only_verifiable", "locally_ready", "safe_fixture_verifiable"}:
            alert_class = "readiness_state"
            severity = "info"
        elif state == "blocked":
            alert_class = "product_blocker"
            severity = "sev3"
        else:
            alert_class = "healthy"
            severity = "none"
        routes.append(
            {
                "surface": section["name"],
                "state": state,
                "alertClass": alert_class,
                "severity": severity,
                "owner": _owner_for_section(section["name"]),
                "routeKey": f"{section['name']}:{alert_class}:{severity}",
                "lowCardinalityDimensions": {
                    "surface": section["name"],
                    "state": state,
                    "alertClass": alert_class,
                    "severity": severity,
                },
                "blockerCategories": section["blockers"][:10],
                "supportActions": section["supportActions"][:10],
                "suppression": "suppress provider_blocker when blocker is known and unchanged during active incident window",
            }
        )

    live_alerting_configured = bool(settings.apm_provider.strip() and settings.apm_alert_destination_approved and settings.apm_alerts_enabled)
    blockers = []
    if not settings.apm_provider.strip():
        blockers.append("missing_apm_provider")
    if not settings.apm_alert_destination_approved:
        blockers.append("apm_alert_destination_not_approved")
    if not settings.apm_alerts_enabled:
        blockers.append("apm_alerts_not_enabled")
    return {
        "generatedAt": _now_iso(),
        "schemaVersion": SCHEMA_VERSION,
        "taxonomy": list(TAXONOMY),
        "overallState": "live_ready" if live_alerting_configured else "blocked",
        "liveAlertingConfigured": live_alerting_configured,
        "apmProvider": settings.apm_provider.strip() or "disabled",
        "routes": routes,
        "blockers": blockers,
        "privacy": _privacy_contract(),
        "runbook": {
            "severityPolicy": {
                "sev2": "product regression affecting core flow or aggregate export integrity",
                "sev3": "provider blocker, blocked BI/APM activation, stale data, or support backlog",
                "info": "read-only, local-only, or safe-fixture readiness state",
            },
            "escalation": {
                "product_regression": "backend_oncall",
                "provider_blocker": "release_operations",
                "privacy_violation": "security_privacy_owner",
            },
            "retryBackfill": "rerun warehouse export with the same period and idempotency key after source recovery",
            "knownBlockedStates": ["live_bi_warehouse_not_configured", "bi_warehouse_export_not_enabled", *blockers],
        },
    }


def _export_sources(*, settings: Settings, period: str, limit: int) -> list[dict[str, Any]]:
    curriculum_export = _safe_source(
        "curriculum_warehouse_export",
        lambda: curriculum_analytics_service.warehouse_export(limit=limit),
    )
    curriculum_rows = []
    for item in curriculum_export.get("items", [])[:limit]:
        curriculum_rows.append(
            _row(
                product_surface="curriculum_analytics",
                period=period,
                metric_name="content_quality_total_signals",
                aggregate_count=int((item.get("metrics") or {}).get("totalSignals") or 0),
                status="exported",
                provider_state="locally_ready",
                blocker_category=None,
                support_action="review_curriculum_quality_hotspots",
                source="curriculum_analytics",
            )
        )

    core = _safe_source("core_smoke", core_smoke_service.build_core_smoke_report)
    core_summary = core.get("summary") or {}
    core_rows = [
        _row("release_smoke", period, "check_count", int(core_summary.get("checkCount") or 0), _classify_core_smoke(core), _classify_core_smoke(core), None, "inspect_core_smoke_regressions", "core_smoke"),
        _row("release_smoke", period, "expected_blocked", int(core_summary.get("expectedBlocked") or 0), _classify_core_smoke(core), _classify_core_smoke(core), None, "separate_expected_blocks_from_regressions", "core_smoke"),
    ]

    payment_auth = _safe_source("payment_auth_activation", lambda: external_activation_service.build_payment_auth_smoke_report(settings))
    notification_support = _safe_source("notification_support_activation", lambda: external_activation_service.build_notification_support_smoke_report(settings))
    activation_rows = [
        _row("billing_provider", period, "blocker_count", len(_collect_blockers(payment_auth)), _source_state(payment_auth, "overallState"), _source_state(payment_auth, "overallState"), "provider_blocker" if _collect_blockers(payment_auth) else None, "resolve_payment_or_auth_activation_blockers", "payment_auth_activation"),
        _row("notification_support", period, "blocker_count", len(_collect_blockers(notification_support)), _source_state(notification_support, "overallState"), _source_state(notification_support, "overallState"), "provider_blocker" if _collect_blockers(notification_support) else None, "resolve_notification_or_support_activation_blockers", "notification_support_activation"),
    ]

    return [
        _source_export("curriculum_analytics", _classify_curriculum_export(curriculum_export), curriculum_rows, _collect_blockers(curriculum_export)),
        _source_export("core_smoke", _classify_core_smoke(core), core_rows, _collect_blockers(core)),
        _source_export("external_activation", _combined_state([payment_auth, notification_support]), activation_rows, _unique([*_collect_blockers(payment_auth), *_collect_blockers(notification_support)])),
    ]


def _row(
    product_surface: str,
    period: str,
    metric_name: str,
    aggregate_count: int,
    status: str,
    provider_state: str,
    blocker_category: str | None,
    support_action: str,
    source: str,
) -> dict[str, Any]:
    row_id = _stable_key(product_surface, period, metric_name, source)
    return {
        "rowId": row_id,
        "schemaVersion": SCHEMA_VERSION,
        "productSurface": product_surface,
        "period": period,
        "metricName": metric_name,
        "aggregateCount": aggregate_count,
        "status": _normalize_state(status),
        "providerState": _normalize_state(provider_state),
        "blockerCategory": blocker_category,
        "supportAction": support_action,
        "source": source,
        "partial": False,
        "stale": False,
    }


def _source_export(name: str, state: str, rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    return {"name": name, "state": _normalize_state(state), "rows": rows, "partial": state in {"unknown", "failed"}, "stale": False, "blockers": blockers}


def _readiness_source(name: str, route: str, state: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_state(state)
    return {
        "name": name,
        "route": route,
        "state": normalized,
        "partial": normalized in {"unknown", "failed"},
        "stale": bool(payload.get("stale")),
        "blockers": _collect_blockers(payload),
        "warnings": _collect_warnings(payload),
    }


def _dashboard_section(
    name: str,
    state: str,
    aggregate: dict[str, Any],
    *,
    blockers: list[str],
    support_actions: list[str] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_state(state)
    return {
        "name": name,
        "state": normalized,
        "aggregate": aggregate,
        "blockers": _unique(blockers),
        "supportActions": support_actions or _support_actions(name, blockers),
        "partial": normalized in {"unknown", "failed"},
        "stale": False,
        "privacy": _privacy_contract(),
    }


def _safe_source(name: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = func()
        if not isinstance(payload, dict):
            return {"state": "unknown", "blockers": [f"{name}_returned_non_object"]}
        return payload
    except Exception as exc:  # noqa: BLE001
        return {
            "state": "failed",
            "status": "failed",
            "blockers": [f"{name}_unavailable"],
            "errorClass": exc.__class__.__name__,
        }


def _classify_curriculum_readiness(payload: dict[str, Any]) -> str:
    state = str(payload.get("state") or "unknown")
    if state == "api-ready":
        return "locally_ready"
    if state == "empty":
        return "read_only_verifiable"
    return _normalize_state(state)


def _classify_curriculum_export(payload: dict[str, Any]) -> str:
    if payload.get("state") == "failed":
        return "failed"
    if int(payload.get("count") or 0) > 0:
        return "locally_ready"
    return "read_only_verifiable"


def _classify_curriculum_dashboard(payload: dict[str, Any]) -> str:
    if payload.get("state") == "failed":
        return "failed"
    if int(payload.get("sampleSize") or 0) > 0:
        return "locally_ready"
    return "read_only_verifiable"


def _classify_core_smoke(payload: dict[str, Any]) -> str:
    if payload.get("state") == "failed" or payload.get("status") == "failed":
        return "failed"
    if payload.get("status") == "ready_with_expected_blocks":
        return "locally_ready"
    if payload.get("status") == "ready":
        return "live_ready"
    return "unknown"


def _classify_payment(payload: dict[str, Any]) -> str:
    if payload.get("state") == "provider_api_failed":
        return "failed"
    if payload.get("checkoutAllowed"):
        return "live_ready"
    if _collect_blockers(payload):
        return "blocked"
    return "read_only_verifiable"


def _classify_notification(payload: dict[str, Any]) -> str:
    if payload.get("state") == "failed":
        return "failed"
    blockers = _unique([*(payload.get("emailProvider") or {}).get("blockers", []), *(payload.get("pushProvider") or {}).get("blockers", [])])
    if blockers:
        return "blocked"
    if (payload.get("emailProvider") or {}).get("mode") == "provider_ready" or (payload.get("pushProvider") or {}).get("mode") == "provider_ready":
        return "live_ready"
    return "read_only_verifiable"


def _classify_support(payload: dict[str, Any]) -> str:
    if payload.get("state") == "failed":
        return "failed"
    provider = payload.get("provider") or {}
    if int(provider.get("failure_count") or 0) > 0:
        return "failed"
    return "read_only_verifiable"


def _combined_state(payloads: list[dict[str, Any]]) -> str:
    states = [_source_state(payload, "overallState") for payload in payloads]
    if "failed" in states:
        return "failed"
    if "blocked" in states:
        return "blocked"
    if "read_only_verifiable" in states:
        return "read_only_verifiable"
    if states and all(state == "live_ready" for state in states):
        return "live_ready"
    return "unknown"


def _source_state(payload: dict[str, Any], key: str) -> str:
    return _normalize_state(str(payload.get(key) or payload.get("state") or payload.get("status") or "unknown"))


def _normalize_state(state: str) -> str:
    normalized = state.replace("-", "_")
    aliases = {
        "api_ready": "locally_ready",
        "empty": "read_only_verifiable",
        "ready_with_expected_blocks": "locally_ready",
        "not_configured": "blocked",
        "provider_api_failed": "failed",
    }
    return aliases.get(normalized, normalized if normalized in TAXONOMY else "unknown")


def _billing_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": payload.get("state"),
        "checkoutAllowed": bool(payload.get("checkoutAllowed")),
        "refundsAllowed": bool(payload.get("refundsAllowed")),
        "providerMode": payload.get("providerMode"),
    }


def _curriculum_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sampleSize": int(payload.get("sampleSize") or 0),
        "summary": payload.get("summary") or {},
        "emptyState": payload.get("emptyState"),
    }


def _notification_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "recentEventCount": int(payload.get("recentEventCount") or 0),
        "websocketMode": payload.get("websocketMode"),
        "emailMode": (payload.get("emailProvider") or {}).get("mode"),
        "pushMode": (payload.get("pushProvider") or {}).get("mode"),
    }


def _support_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sampleSize": int(payload.get("sample_size") or 0),
        "statusCounts": payload.get("status_counts") or {},
        "provider": payload.get("provider") or {},
        "retry": payload.get("retry") or {},
    }


def _support_actions(name: str, blockers: list[str]) -> list[str]:
    if blockers:
        return [f"resolve_{blocker}" for blocker in blockers[:5]]
    return [f"monitor_{name}"]


def _owner_for_section(name: str) -> str:
    if name in {"billing_provider", "notification_delivery", "teacher_help_support", "warehouse_export"}:
        return "release_operations"
    if name in {"curriculum_analytics", "usage_quota"}:
        return "product_operations"
    return "backend_oncall"


def _collect_blockers(payload: dict[str, Any]) -> list[str]:
    blockers = list(payload.get("blockers") or [])
    for key in ("payment", "cognitoEmail", "notification", "support", "emailProvider", "pushProvider"):
        section = payload.get(key)
        if isinstance(section, dict):
            blockers.extend(section.get("blockers") or [])
    return _unique([str(item) for item in blockers if item])


def _collect_warnings(payload: dict[str, Any]) -> list[str]:
    warnings = list(payload.get("warnings") or [])
    for key in ("payment", "cognitoEmail", "notification", "support"):
        section = payload.get(key)
        if isinstance(section, dict):
            warnings.extend(section.get("warnings") or [])
    return _unique([str(item) for item in warnings if item])


def _privacy_contract() -> dict[str, Any]:
    return {
        "aggregateOnly": True,
        "rawStudentContentIncluded": False,
        "rawProviderPayloadsIncluded": False,
        "secretsIncluded": False,
        "highCardinalityPrivateIdentifiersIncluded": False,
        "privateArtifactKeysIncluded": False,
        "forbiddenFields": list(FORBIDDEN_FIELDS),
    }


def _stable_key(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"bi_{digest}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
