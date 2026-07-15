"""Dry-run-first privileged identity inventory and auto-tightening planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Iterable, Mapping, Protocol


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
    version: int = 1


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

    @property
    def privilege_increase(self) -> bool:
        return self.action in PRIVILEGE_INCREASE_ACTIONS


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    item_id: str
    classification: str
    reason: str
    before: Mapping[str, Any]
    after: Mapping[str, Any]
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

    def safe_projection(self) -> dict[str, Any]:
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
    def revoke_grant(self, user_id: str, grant: GrantSnapshot, *, action_id: str) -> None: ...
    def append_audit(self, item_id: str, action: str, *, action_id: str) -> None: ...


@dataclass(slots=True)
class MemoryCheckpointStore:
    completed: set[str] = field(default_factory=set)

    def contains(self, action_id: str) -> bool:
        return action_id in self.completed

    def mark(self, action_id: str) -> None:
        self.completed.add(action_id)


def _safe_state(snapshot: IdentitySnapshot) -> dict[str, Any]:
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
        for grant in invalid_grants:
            actions.append(ReconciliationAction("remove_grant", reason, grant.grant_id))

    before = _safe_state(snapshot)
    after = dict(before)
    if actions:
        after.update(profileStatus="suspended_pending_review", privilegedGroupCount=0)
        after["grantCount"] = max(0, len(snapshot.grants) - len(invalid_grants))
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
    store = checkpoints or MemoryCheckpointStore()
    snapshots_by_id = {
        redacted_item_id(item.issuer, item.provider_subject, item.user_id or "missing"): item
        for item in snapshots
    }
    applied: list[str] = []
    skipped: list[str] = []
    for item in items:
        snapshot = snapshots_by_id[item.item_id]
        for index, action in enumerate(item.actions):
            action_id = f"{item.checkpoint}:{index}:{action.action}"
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
                grant = next(grant for grant in snapshot.grants if grant.grant_id == action.target)
                adapter.revoke_grant(snapshot.user_id, grant, action_id=action_id)
            else:
                raise RuntimeError(f"unsupported automatic action: {action.action}")
            adapter.append_audit(item.item_id, action.action, action_id=action_id)
            store.mark(action_id)
            applied.append(action_id)
    return ReconciliationReport(run_id, "apply-tightening", items, tuple(applied), tuple(skipped))


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
    def revoke_grant(self, user_id: str, grant: GrantSnapshot, *, action_id: str) -> None: pass
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
