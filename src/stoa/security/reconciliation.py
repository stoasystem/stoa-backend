"""Dry-run-first privileged identity inventory and auto-tightening planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from collections.abc import Callable, Iterable, Mapping
from typing import Protocol


CANONICAL_ROLES = frozenset({"student", "parent", "teacher", "admin"})
PRIVILEGED_ROLES = frozenset({"teacher", "admin"})
PRIVILEGED_GROUPS = frozenset({"teachers", "admins"})
LEGACY_TEACHER_ROLE = "tu" + "tor"
LEGACY_TEACHER_GROUP = LEGACY_TEACHER_ROLE + "s"
PRIVILEGE_INCREASE_ACTIONS = frozenset(
    {"add_group", "restore_account", "grant_capability", "activate_account"}
)


def redacted_item_id(*values: str) -> str:
    material = "\x1f".join(value.strip() for value in values)
    return f"identity_{sha256(material.encode()).hexdigest()[:20]}"


@dataclass(frozen=True, slots=True)
class GrantSnapshot:
    grant_id: str
    capability: str
    scope: str
    status: str = "active"
    generation: int = 1
    version: int = 1


@dataclass(frozen=True, slots=True)
class GrantCoordinate:
    """Lossless immutable address of one capability grant revision."""

    capability: str
    scope: str
    generation: int
    grant_id: str
    version: int

    @classmethod
    def from_snapshot(cls, grant: GrantSnapshot) -> GrantCoordinate:
        return cls(
            capability=grant.capability,
            scope=grant.scope,
            generation=grant.generation,
            grant_id=grant.grant_id,
            version=grant.version,
        )

    def validate(self) -> None:
        strings = (self.capability, self.scope, self.grant_id)
        if any(not isinstance(value, str) or not value.strip() for value in strings):
            raise ValueError("complete grant coordinate fields are required")
        if any(value != value.strip() for value in strings):
            raise ValueError("grant coordinate fields must be canonical")
        if (
            isinstance(self.generation, bool)
            or isinstance(self.version, bool)
            or not isinstance(self.generation, int)
            or not isinstance(self.version, int)
            or self.generation < 1
            or self.version < 1
        ):
            raise ValueError("positive grant generation and version are required")

    def canonical_material(self) -> str:
        return "\x1f".join(
            (
                self.capability,
                self.scope,
                str(self.generation),
                self.grant_id,
                str(self.version),
            )
        )


@dataclass(frozen=True, slots=True)
class IdentitySnapshot:
    provider_subject: str
    issuer: str
    groups: tuple[str, ...]
    user_id: str | None
    profile_role: str | None
    profile_status: str | None
    binding_count: int
    approved: bool
    grants: tuple[GrantSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationAction:
    action: str
    reason: str
    target: str | None = None
    grant_coordinate: GrantCoordinate | None = None

    def __post_init__(self) -> None:
        if self.action == "remove_grant":
            if self.grant_coordinate is None or self.target is not None:
                raise ValueError("remove_grant requires one full grant coordinate")
        elif self.grant_coordinate is not None:
            raise ValueError("grant coordinates are valid only for remove_grant")

    @property
    def privilege_increase(self) -> bool:
        return self.action in PRIVILEGE_INCREASE_ACTIONS


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    item_id: str
    classification: str
    reason: str
    before: Mapping[str, object]
    after: Mapping[str, object]
    actions: tuple[ReconciliationAction, ...]
    checkpoint: str
    manual_approval_required: bool = False


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    run_id: str
    mode: str
    items: tuple[ReconciliationItem, ...]
    applied_actions: tuple[str, ...] = ()
    skipped_actions: tuple[str, ...] = ()
    added_roles: tuple[str, ...] = ()
    added_grants: tuple[str, ...] = ()

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(action.action for item in self.items for action in item.actions)

    def safe_projection(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "mode": self.mode,
            "items": [
                {
                    "itemId": item.item_id,
                    "classification": item.classification,
                    "reason": item.reason,
                    "before": dict(item.before),
                    "after": dict(item.after),
                    "actions": [
                        {"action": action.action, "reason": action.reason}
                        for action in item.actions
                    ],
                    "checkpoint": item.checkpoint,
                    "manualApprovalRequired": item.manual_approval_required,
                }
                for item in self.items
            ],
            "appliedActions": list(self.applied_actions),
            "skippedActions": list(self.skipped_actions),
            "addedRoles": [],
            "addedGrants": [],
        }


class TighteningAdapter(Protocol):
    def suspend_local(self, user_id: str, *, action_id: str) -> None: ...
    def remove_group(self, provider_subject: str, group: str, *, action_id: str) -> None: ...
    def global_sign_out(self, provider_subject: str, *, action_id: str) -> None: ...
    def revoke_grant(self, user_id: str, grant: GrantCoordinate, *, action_id: str) -> None: ...
    def append_audit(self, item_id: str, action: str, *, action_id: str) -> None: ...


class LocalAccountTightening(Protocol):
    def suspend_local(self, user_id: str, *, action_id: str) -> None: ...


class ProviderGroupTightening(Protocol):
    def remove_group(self, provider_subject: str, group: str, *, action_id: str) -> None: ...
    def global_sign_out(self, provider_subject: str, *, action_id: str) -> None: ...


class CapabilityGrantTightening(Protocol):
    def revoke_capability(
        self,
        *,
        user_id: str,
        grant_id: str,
        capability: str,
        scope: str,
        expected_generation: int,
        expected_version: int,
        actor_id: str,
        reason: str,
        changed_at: str,
        action_id: str,
    ) -> object: ...


class ReconciliationAuditRepository(Protocol):
    DuplicateSecurityAuditEvent: type[Exception] | tuple[type[Exception], ...]

    def append_event(self, item_id: str, event: Mapping[str, object]) -> object: ...


class RepositoryTighteningAdapter:
    """Concrete conditional adapter for explicitly authorized tightening runs."""

    def __init__(
        self,
        *,
        local_account: LocalAccountTightening,
        provider: ProviderGroupTightening,
        capability_repository: CapabilityGrantTightening,
        audit_repository: ReconciliationAuditRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        required = (local_account, provider, capability_repository, audit_repository)
        if any(collaborator is None for collaborator in required):
            raise ValueError("all tightening collaborators are required")
        self._local = local_account
        self._provider = provider
        self._capabilities = capability_repository
        self._audit = audit_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def suspend_local(self, user_id: str, *, action_id: str) -> None:
        self._local.suspend_local(user_id, action_id=action_id)

    def remove_group(self, provider_subject: str, group: str, *, action_id: str) -> None:
        self._provider.remove_group(provider_subject, group, action_id=action_id)

    def global_sign_out(self, provider_subject: str, *, action_id: str) -> None:
        self._provider.global_sign_out(provider_subject, action_id=action_id)

    def revoke_grant(self, user_id: str, grant: GrantCoordinate, *, action_id: str) -> None:
        grant.validate()
        instant = self._clock()
        changed_at = instant.isoformat()
        self._capabilities.revoke_capability(
            user_id=user_id,
            grant_id=grant.grant_id,
            capability=grant.capability,
            scope=grant.scope,
            expected_generation=grant.generation,
            expected_version=grant.version,
            actor_id="privileged_identity_reconciliation",
            reason="privileged_identity_conflict",
            changed_at=changed_at,
            action_id=action_id,
        )

    def append_audit(self, item_id: str, action: str, *, action_id: str) -> None:
        instant = self._clock()
        created_at = instant.isoformat()
        event = {
            "event_id": action_id,
            "event_type": "privileged_capability_quarantined",
            "target_type": "privileged_identity",
            "action": action,
            "result_code": "tightened",
            "reason_code": "privileged_identity_conflict",
            "evidence_reference": f"reconciliation:{action_id}",
            "created_at": created_at,
        }
        try:
            self._audit.append_event(item_id, event)
        except Exception as exc:
            duplicate = self._audit.DuplicateSecurityAuditEvent
            if isinstance(exc, duplicate):
                return
            raise


@dataclass(slots=True)
class MemoryCheckpointStore:
    completed: set[str] = field(default_factory=set)

    def contains(self, action_id: str) -> bool:
        return action_id in self.completed

    def mark(self, action_id: str) -> None:
        self.completed.add(action_id)


def _safe_state(snapshot: IdentitySnapshot) -> dict[str, object]:
    recognized_groups = sorted(group for group in snapshot.groups if group in PRIVILEGED_GROUPS)
    return {
        "groupCount": len(snapshot.groups),
        "privilegedGroupCount": len(recognized_groups),
        "profileRole": snapshot.profile_role if snapshot.profile_role in CANONICAL_ROLES else "invalid",
        "profileStatus": snapshot.profile_status or "missing",
        "bindingCount": snapshot.binding_count,
        "grantCount": len(snapshot.grants),
        "approved": snapshot.approved,
    }


def plan_identity(snapshot: IdentitySnapshot, *, run_id: str) -> ReconciliationItem:
    item_id = redacted_item_id(snapshot.issuer, snapshot.provider_subject, snapshot.user_id or "missing")
    privileged_groups = tuple(group for group in snapshot.groups if group in PRIVILEGED_GROUPS)
    legacy_groups = tuple(
        group
        for group in snapshot.groups
        if group.lower() in {LEGACY_TEACHER_ROLE, LEGACY_TEACHER_GROUP}
    )
    invalid_grants = tuple(
        grant for grant in snapshot.grants
        if grant.status != "active" or grant.version < 1 or not grant.capability or not grant.scope
    )
    expected_group = {
        "teacher": "teachers",
        "admin": "admins",
    }.get(snapshot.profile_role or "")
    classification = "exact_approved_active_match"
    reason = "approved active privileged identity matches provider and local authority"
    actions: list[ReconciliationAction] = []

    if legacy_groups or snapshot.profile_role == LEGACY_TEACHER_ROLE:
        classification, reason = "historical_tutor", "historical teacher terminology is conflicted"
    elif snapshot.user_id is None or snapshot.profile_role not in CANONICAL_ROLES:
        classification, reason = "unknown", "identity has no canonical local profile"
    elif not snapshot.approved:
        classification, reason = "missing_approval", "privileged identity lacks approval evidence"
    elif snapshot.profile_status != "active":
        classification, reason = "inactive", "local profile is not active"
    elif snapshot.binding_count != 1:
        classification = "missing_binding" if snapshot.binding_count == 0 else "duplicate_binding"
        reason = "identity requires exactly one authoritative binding"
    elif len(privileged_groups) > 1:
        classification, reason = "multiple_roles", "multiple privileged groups are an identity conflict"
    elif expected_group and privileged_groups != (expected_group,):
        classification, reason = "local_group_mismatch", "provider group and local role disagree"
    elif invalid_grants:
        classification, reason = "invalid_capability_version", "grant status or version is invalid"

    if classification != "exact_approved_active_match":
        if snapshot.profile_status not in {"suspended", "revoked", "disabled", "deleted"}:
            actions.append(ReconciliationAction("suspend_pending_review", reason))
        for group in sorted(set(privileged_groups + legacy_groups)):
            actions.append(ReconciliationAction("remove_group", reason, group))
        if privileged_groups or legacy_groups:
            actions.append(ReconciliationAction("global_sign_out", reason))
        for grant in sorted(
            snapshot.grants,
            key=lambda value: (
                value.capability,
                value.scope,
                value.generation,
                value.grant_id,
                value.version,
            ),
        ):
            actions.append(
                ReconciliationAction(
                    "remove_grant",
                    reason,
                    grant_coordinate=GrantCoordinate.from_snapshot(grant),
                )
            )

    before = _safe_state(snapshot)
    after = dict(before)
    if actions:
        after.update(profileStatus="suspended_pending_review", privilegedGroupCount=0)
        after["grantCount"] = 0
    checkpoint = sha256(f"{run_id}:{item_id}".encode()).hexdigest()[:24]
    return ReconciliationItem(
        item_id, classification, reason, before, after, tuple(actions), checkpoint,
        manual_approval_required=classification != "exact_approved_active_match",
    )


def reconcile_inventory(
    snapshots: Iterable[IdentitySnapshot],
    *,
    run_id: str,
    apply: bool = False,
    environment: str | None = None,
    confirmation: str | None = None,
    approved_run_id: str | None = None,
    adapter: TighteningAdapter | None = None,
    checkpoints: MemoryCheckpointStore | None = None,
) -> ReconciliationReport:
    if not run_id.strip():
        raise ValueError("run_id is required")
    snapshots = tuple(snapshots)
    items = tuple(sorted((plan_identity(item, run_id=run_id) for item in snapshots), key=lambda item: item.item_id))
    if not apply:
        return ReconciliationReport(run_id, "dry-run", items)
    if environment in {None, "", "production"}:
        raise PermissionError("apply requires an explicit non-production environment")
    if confirmation != "APPLY_TIGHTENING" or approved_run_id != run_id:
        raise PermissionError("apply requires separate confirmation and the approved run id")
    if adapter is None:
        raise PermissionError("apply requires an injected tightening adapter")
    _validate_apply_actions(items)
    store = checkpoints or MemoryCheckpointStore()
    snapshots_by_id = {
        redacted_item_id(item.issuer, item.provider_subject, item.user_id or "missing"): item
        for item in snapshots
    }
    applied: list[str] = []
    skipped: list[str] = []
    for item in items:
        snapshot = snapshots_by_id[item.item_id]
        for action in item.actions:
            action_id = _action_id(item, action)
            if store.contains(action_id):
                skipped.append(action_id)
                continue
            if action.privilege_increase:
                raise PermissionError("manual_approval_required: use active admin_identity_manager command")
            if action.action == "suspend_pending_review":
                if snapshot.user_id:
                    adapter.suspend_local(snapshot.user_id, action_id=action_id)
            elif action.action == "remove_group":
                adapter.remove_group(snapshot.provider_subject, str(action.target), action_id=action_id)
            elif action.action == "global_sign_out":
                adapter.global_sign_out(snapshot.provider_subject, action_id=action_id)
            elif action.action == "remove_grant" and snapshot.user_id:
                coordinate = action.grant_coordinate
                if coordinate is None:
                    raise ValueError("remove_grant requires one full grant coordinate")
                adapter.revoke_grant(
                    snapshot.user_id,
                    coordinate,
                    action_id=action_id,
                )
            else:
                raise RuntimeError(f"unsupported automatic action: {action.action}")
            adapter.append_audit(item.item_id, action.action, action_id=action_id)
            store.mark(action_id)
            applied.append(action_id)
    return ReconciliationReport(run_id, "apply-tightening", items, tuple(applied), tuple(skipped))


def _validate_apply_actions(items: tuple[ReconciliationItem, ...]) -> None:
    """Fail before the first mutation if any planned grant address is unsafe."""
    seen: set[tuple[str, GrantCoordinate]] = set()
    for item in items:
        for action in item.actions:
            if action.action != "remove_grant":
                continue
            coordinate = action.grant_coordinate
            if coordinate is None:  # Defensive for deserialized/legacy callers.
                raise ValueError("remove_grant requires one full grant coordinate")
            coordinate.validate()
            identity = (item.item_id, coordinate)
            if identity in seen:
                raise ValueError("duplicate grant coordinate in reconciliation item")
            seen.add(identity)


def _action_id(item: ReconciliationItem, action: ReconciliationAction) -> str:
    if action.grant_coordinate is not None:
        semantic_target = action.grant_coordinate.canonical_material()
    else:
        semantic_target = action.target or ""
    digest = sha256(
        "\x1f".join((item.item_id, action.action, semantic_target)).encode("utf-8")
    ).hexdigest()[:24]
    return f"{item.checkpoint}:{action.action}:{digest}"


_CASES = {
    "excess-group": IdentitySnapshot("sub-1", "issuer", ("admins", "teachers"), "user-1", "admin", "active", 1, True),
    "multiple-role-groups": IdentitySnapshot("sub-2", "issuer", ("admins", "teachers"), "user-2", "admin", "active", 1, True),
    f"historical-{LEGACY_TEACHER_ROLE}-role": IdentitySnapshot(
        "sub-3", "issuer", (LEGACY_TEACHER_GROUP,), "user-3",
        LEGACY_TEACHER_ROLE, "active", 1, False,
    ),
    "unknown-privileged-identity": IdentitySnapshot("sub-4", "issuer", ("admins",), None, None, None, 0, False),
    "active-grant-revoked": IdentitySnapshot("sub-5", "issuer", ("admins",), "user-5", "admin", "active", 1, True, (GrantSnapshot("grant-1", "student_support_lookup", "global", "revoked", 2),)),
    "provider-canary": IdentitySnapshot("provider-payload-canary", "issuer", ("admins", "teachers"), "user-canary", "admin", "active", 1, True),
}
_CASE_CHECKPOINTS = MemoryCheckpointStore()


class _RecordingAdapter:
    def suspend_local(self, user_id: str, *, action_id: str) -> None: pass
    def remove_group(self, provider_subject: str, group: str, *, action_id: str) -> None: pass
    def global_sign_out(self, provider_subject: str, *, action_id: str) -> None: pass
    def revoke_grant(self, user_id: str, grant: GrantCoordinate, *, action_id: str) -> None: pass
    def append_audit(self, item_id: str, action: str, *, action_id: str) -> None: pass


def reconcile_case(case: str, *, dry_run: bool, checkpoint: str | None = None) -> ReconciliationReport:
    snapshot = _CASES[case]
    report = reconcile_inventory(
        [snapshot], run_id=checkpoint or f"dry-{case}", apply=not dry_run,
        environment="test" if not dry_run else None,
        confirmation="APPLY_TIGHTENING" if not dry_run else None,
        approved_run_id=checkpoint if not dry_run else None,
        adapter=_RecordingAdapter() if not dry_run else None,
        checkpoints=_CASE_CHECKPOINTS,
    )
    if dry_run:
        return report
    return ReconciliationReport(report.run_id, report.mode, report.items)
