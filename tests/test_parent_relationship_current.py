"""One judge, five outlets: a parent-student relationship is judged, never inferred.

Issues #2, #3, #4, #8, #15 were five readings of the same defect - two key spaces
hold relationships (`parent_student_binding` and `parent_student_link`), a
student profile's `parent_id` holds neither, and every read path decided for
itself which of the three to believe. `parent_link_service.current_relationship`
is now the only answer, and each test below pairs its refusal with the positive
case, so a change that refuses everything cannot pass.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable

from stoa.config import Settings

from stoa.db.repositories import account_deletion_repo, parent_link_repo, user_repo
from stoa.jobs import weekly_reports
from stoa.services import (
    account_deletion_service,
    account_operations_service,
    entitlement_service,
    parent_link_service,
    report_recovery_service,
    report_service,
)

from test_parent_student_links import FakeLinkTable, _parent_app


NOW = "2026-09-19T10:00:00+00:00"
PARENT = "parent-1"
STUDENT = "student-1"


def _profile(user_id: str, role: str, *, account_status: str = "active") -> dict[str, Any]:
    return {
        # The shape the table actually stores a profile at. The double this
        # fixture used to feed did not need the key, which is how a row that no
        # real scan could return became the thing under test.
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": account_status,
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        "date_of_birth": "2000-01-01",
    }


def _binding(parent_id: str, student_id: str, status: str = "active") -> dict[str, Any]:
    return {
        "entity_type": "parent_student_binding",
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": "child",
        "status": status,
        "version": 1,
    }


class RelationshipWorld:
    """The two relationship key spaces plus the profiles behind them."""

    def __init__(self) -> None:
        self.table = FakeLinkTable()
        self.profiles: dict[str, dict[str, Any]] = {}
        self.bindings: dict[tuple[str, str], dict[str, Any]] = {}

    def account(self, user_id: str, role: str, **kwargs: Any) -> str:
        self.profiles[user_id] = _profile(user_id, role, **kwargs)
        self.table.seed_account_fence(user_id)
        return user_id

    def bind(self, parent_id: str, student_id: str, status: str = "active") -> None:
        """A legacy binding, in both formal rows and the profile projection."""
        self.bindings[(parent_id, student_id)] = _binding(parent_id, student_id, status)
        self.profiles[student_id]["parent_id"] = parent_id
        self.profiles[student_id]["relationship"] = "child"
        self.profiles[student_id]["parent_binding_status"] = status

    def revoke_binding(self, parent_id: str, student_id: str) -> None:
        """What revocation does: the rows go to `revoked`, the projection follows."""
        self.bind(parent_id, student_id, status="revoked")

    def strand_profile_only(self, parent_id: str, student_id: str) -> None:
        """The binding rows are gone; only the profile still names the parent."""
        self.bindings.pop((parent_id, student_id), None)
        self.profiles[student_id]["parent_id"] = parent_id
        self.profiles[student_id]["parent_binding_status"] = "active"

    def link(self, parent_id: str, student_id: str) -> None:
        parent_link_service.assign_link(
            parent_id=parent_id, student_id=student_id, actor_id="admin-1", now=NOW
        )

    def install(self, monkeypatch: pytest.MonkeyPatch) -> RelationshipWorld:
        monkeypatch.setattr(parent_link_repo, "get_table", lambda: self.table)
        monkeypatch.setattr(
            user_repo, "get_user", lambda user_id, **_k: deepcopy(self.profiles.get(user_id))
        )
        monkeypatch.setattr(
            user_repo,
            "get_parent_student_binding",
            lambda parent_id, student_id: deepcopy(self.bindings.get((parent_id, student_id))),
        )
        monkeypatch.setattr(
            user_repo,
            "get_student_parent_binding",
            lambda student_id, parent_id: deepcopy(self.bindings.get((parent_id, student_id))),
        )
        monkeypatch.setattr(
            user_repo,
            "list_parent_student_bindings",
            lambda parent_id: [
                deepcopy(row) for (pid, _sid), row in self.bindings.items() if pid == parent_id
            ],
        )
        monkeypatch.setattr(
            user_repo,
            "list_student_parent_bindings",
            lambda student_id: [
                deepcopy(row) for (_pid, sid), row in self.bindings.items() if sid == student_id
            ],
        )
        monkeypatch.setattr(
            user_repo,
            "list_children_by_parent_scan",
            lambda parent_id: [
                deepcopy(profile)
                for profile in self.profiles.values()
                if profile.get("role") == "student" and profile.get("parent_id") == parent_id
            ],
        )
        return self


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> RelationshipWorld:
    built = RelationshipWorld()
    built.account(PARENT, "parent")
    built.account(STUDENT, "student")
    return built.install(monkeypatch)


# ---------------------------------------------------------------------------
# The judge itself
# ---------------------------------------------------------------------------


def test_an_active_legacy_binding_is_a_current_relationship(world: RelationshipWorld) -> None:
    world.bind(PARENT, STUDENT)

    relationship = parent_link_service.current_relationship(PARENT, STUDENT)

    assert relationship is not None
    assert relationship["source"] == "parent_student_binding"


def test_an_active_new_link_is_a_current_relationship(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)

    relationship = parent_link_service.current_relationship(PARENT, STUDENT)

    assert relationship is not None
    assert relationship["source"] == "parent_student_link"


def test_a_revoked_binding_is_not_a_current_relationship(world: RelationshipWorld) -> None:
    world.revoke_binding(PARENT, STUDENT)

    assert parent_link_service.current_relationship(PARENT, STUDENT) is None


def test_a_profile_parent_id_alone_is_not_a_current_relationship(
    world: RelationshipWorld,
) -> None:
    world.strand_profile_only(PARENT, STUDENT)

    assert world.profiles[STUDENT]["parent_id"] == PARENT
    assert parent_link_service.current_relationship(PARENT, STUDENT) is None


def test_one_sided_binding_rows_are_not_a_current_relationship(
    world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.bind(PARENT, STUDENT)
    monkeypatch.setattr(user_repo, "get_student_parent_binding", lambda _s, _p: None)

    assert parent_link_service.current_relationship(PARENT, STUDENT) is None


def test_current_children_gathers_both_key_spaces(world: RelationshipWorld) -> None:
    world.account("student-2", "student")
    world.bind(PARENT, STUDENT)
    world.link(PARENT, "student-2")
    world.account("student-3", "student")
    world.revoke_binding(PARENT, "student-3")

    seen = {row["student_id"] for row in parent_link_service.current_children(PARENT)}

    assert seen == {STUDENT, "student-2"}


# ---------------------------------------------------------------------------
# Issue #2: GET /parents/me/account-operations
# ---------------------------------------------------------------------------


@pytest.fixture
def account_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account_operations_service.subscription_service,
        "get_parent_billing",
        lambda parent_id, *, settings: {"status": "active"},
    )
    monkeypatch.setattr(
        account_operations_service.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, *, settings, student_profile=None: {"effectivePlan": "free_trial"},
    )
    monkeypatch.setattr(
        account_operations_service.usage_ledger_service,
        "build_student_usage_summary",
        lambda *, student_id, settings, day=None, entitlement=None: {
            "studentId": student_id,
            "consumed": 2,
        },
    )


def _operations_children(parent_id: str = PARENT) -> list[dict[str, Any]]:
    client = TestClient(_parent_app(parent_id))
    response = client.get("/parents/me/account-operations")
    assert response.status_code == 200, response.text
    return response.json()["children"]


@pytest.mark.usefixtures("account_operations")
def test_a_current_parent_still_reads_the_child_through_account_operations(
    world: RelationshipWorld,
) -> None:
    """Negative control: the fix must not take the working case away."""
    world.bind(PARENT, STUDENT)

    children = _operations_children()

    assert [child["studentId"] for child in children] == [STUDENT]
    assert children[0]["profile"]["email"] == f"{STUDENT}@stoa.test"


@pytest.mark.usefixtures("account_operations")
def test_a_new_link_child_is_read_through_account_operations(
    world: RelationshipWorld,
) -> None:
    world.link(PARENT, STUDENT)

    assert [child["studentId"] for child in _operations_children()] == [STUDENT]


@pytest.mark.usefixtures("account_operations")
def test_revoked_parent_cannot_read_child_via_account_operations(
    world: RelationshipWorld,
) -> None:
    world.revoke_binding(PARENT, STUDENT)

    children = _operations_children()

    assert children == []
    assert f"{STUDENT}@stoa.test" not in str(children)


@pytest.mark.usefixtures("account_operations")
def test_profile_parent_id_alone_does_not_authorize_operations(
    world: RelationshipWorld,
) -> None:
    world.strand_profile_only(PARENT, STUDENT)

    assert _operations_children() == []


# ---------------------------------------------------------------------------
# Issues #3 and #8: weekly report generation
# ---------------------------------------------------------------------------


@pytest.fixture
def quiet_report_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty shared double, not a hand-written one. The exemption this used to
    # carry said "script", and the gate reserves that for a double driving a
    # repository down a path a real table cannot take; an empty table is not
    # that, and the shared one is empty just as well.
    empty = FakeTable()
    monkeypatch.setattr(report_service, "get_table", lambda: empty)
    monkeypatch.setattr(
        report_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500, last_key=None: {"Items": []},
    )
    monkeypatch.setattr(report_service.practice_repo, "get_progress", lambda _s: [])
    monkeypatch.setattr(report_service.practice_repo, "get_mistakes", lambda _s: [])


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_current_parent_still_gets_a_weekly_report_payload(
    world: RelationshipWorld,
) -> None:
    """Negative control for the two refusals below."""
    world.bind(PARENT, STUDENT)

    payload = report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-06-01")

    assert payload["student"]["id"] == STUDENT


@pytest.mark.usefixtures("quiet_report_sources")
def test_new_admin_assigned_link_can_resolve_student_for_report(
    world: RelationshipWorld,
) -> None:
    world.link(PARENT, STUDENT)

    payload = report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-06-01")

    assert payload["student"]["id"] == STUDENT


@pytest.mark.usefixtures("quiet_report_sources")
def test_revoked_parent_is_rejected_before_weekly_report_payload(
    world: RelationshipWorld,
) -> None:
    world.revoke_binding(PARENT, STUDENT)

    with pytest.raises(ValueError, match="student is not linked"):
        report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-06-01")


@pytest.mark.usefixtures("quiet_report_sources")
def test_stale_profile_parent_id_is_rejected_before_weekly_report_payload(
    world: RelationshipWorld,
) -> None:
    world.strand_profile_only(PARENT, STUDENT)

    with pytest.raises(ValueError, match="student is not linked"):
        report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-06-01")


def _discovery_table(rows: list[dict[str, Any]]) -> FakeTable:
    """The shared double, seeded with these rows.

    The hand-written one this replaces read the accepted entity types out of
    `ExpressionAttributeValues` rather than evaluating the expression, which made
    it blind to the filter: a scan that had stopped naming the link rows got them
    back anyway, and the poison meant to catch that came back green. The shared
    double evaluates the expression, so the same poison goes red.
    """
    table = FakeTable()
    for row in rows:
        table.seed(dict(row))
    return table


def test_new_admin_assigned_link_is_discovered_for_weekly_reports(
    world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.link(PARENT, STUDENT)
    rows = [dict(item) for item in world.table.items.values()]
    monkeypatch.setattr(weekly_reports, "get_table", lambda: _discovery_table(rows))

    assert weekly_reports.eligible_parent_student_pairs() == [
        {"parent_id": PARENT, "student_id": STUDENT}
    ]


def test_a_stale_profile_pair_is_dropped_before_the_weekly_job_runs(
    world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.strand_profile_only(PARENT, STUDENT)
    rows = [deepcopy(world.profiles[STUDENT]) | {"role": "student"}]
    monkeypatch.setattr(weekly_reports, "get_table", lambda: _discovery_table(rows))

    # Discovery still finds it; only the judge drops it.
    assert weekly_reports.discover_linked_parent_student_pairs() == [
        {"parent_id": PARENT, "student_id": STUDENT}
    ]
    assert weekly_reports.eligible_parent_student_pairs() == []


@pytest.fixture
def weekly_job_attempts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Every pair the job would actually claim and generate for."""
    attempts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        weekly_reports.report_service,
        "build_weekly_report_claim",
        lambda parent_id, student_id, week_start: (
            attempts.append((parent_id, student_id)),
            {"report_id": "report-1"},
        )[1],
    )
    monkeypatch.setattr(
        weekly_reports.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner: {"status": "active", "generation": 7},
    )
    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", lambda _c: False)
    return attempts


def test_the_weekly_job_does_not_run_on_a_revoked_pair(
    world: RelationshipWorld,
    weekly_job_attempts: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world.account("student-2", "student")
    world.bind(PARENT, "student-2")
    world.revoke_binding(PARENT, STUDENT)
    rows = [
        _binding(PARENT, STUDENT, "active") | {"PK": f"USER#{PARENT}", "SK": f"CHILD#{STUDENT}"},
        _binding(PARENT, "student-2") | {"PK": f"USER#{PARENT}", "SK": "CHILD#student-2"},
    ]
    monkeypatch.setattr(weekly_reports, "get_table", lambda: _discovery_table(rows))

    weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    # The revoked pair is still discoverable, so this is the job's own filter.
    assert weekly_job_attempts == [(PARENT, "student-2")]


# ---------------------------------------------------------------------------
# Issue #3: resend
# ---------------------------------------------------------------------------


def _failed_report() -> dict[str, Any]:
    return {
        "report_id": "report-1",
        "parent_id": PARENT,
        "student_id": STUDENT,
        "student_name": "Student",
        # The address the relationship had when the artifact was written.
        "parent_email": "archived@stoa.test",
        "week_start": "2026-06-01",
        "status": "email_failed",
        "email_status": "failed",
        "html_s3_key": "weekly-reports/private/report.html",
    }


@pytest.fixture
def resend_doubles(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        report_recovery_service.report_artifact_service,
        "get_report_html",
        lambda _key: "<html>Report</html>",
    )
    monkeypatch.setattr(
        report_recovery_service.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner: {"status": "active", "generation": 7},
    )
    monkeypatch.setattr(
        report_recovery_service.notify_service,
        "send_fenced_weekly_report_email",
        lambda email, html, **_kwargs: (sent.append((email, html)), "accepted")[1],
    )
    monkeypatch.setattr(
        report_recovery_service.report_repo,
        "update_report_status",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        report_recovery_service.report_repo, "put_report_audit_event", lambda *_a, **_k: None
    )
    return sent


def test_a_current_parent_still_receives_a_resend(
    world: RelationshipWorld, resend_doubles: list[tuple[str, str]]
) -> None:
    """Negative control, and the proof that the recipient is resolved again."""
    world.bind(PARENT, STUDENT)

    result = report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert result.status == "email_sent"
    assert resend_doubles == [(f"{PARENT}@stoa.test", "<html>Report</html>")]


def test_report_recovery_does_not_send_to_a_revoked_parent(
    world: RelationshipWorld, resend_doubles: list[tuple[str, str]]
) -> None:
    world.revoke_binding(PARENT, STUDENT)

    with pytest.raises(report_recovery_service.ReportRecoveryError) as refused:
        report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert refused.value.status_code == 403
    assert resend_doubles == []


def test_report_recovery_does_not_send_to_a_stale_profile_parent(
    world: RelationshipWorld, resend_doubles: list[tuple[str, str]]
) -> None:
    world.strand_profile_only(PARENT, STUDENT)

    with pytest.raises(report_recovery_service.ReportRecoveryError):
        report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert resend_doubles == []


# ---------------------------------------------------------------------------
# Issue #15: writes are fenced on both participants' account fences
# ---------------------------------------------------------------------------


def test_link_assignment_succeeds_while_both_fences_are_active(
    world: RelationshipWorld,
) -> None:
    """Negative control: closing this must not close every assignment."""
    world.link(PARENT, STUDENT)

    assert parent_link_service.active_link(PARENT, STUDENT) is not None


@pytest.mark.parametrize("deleting", [PARENT, STUDENT], ids=["parent", "student"])
def test_link_assignment_refuses_either_deletion_pending_account(
    world: RelationshipWorld, deleting: str
) -> None:
    world.table.seed_account_fence(deleting, status="deletion_pending", generation=2)

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        world.link(PARENT, STUDENT)

    assert ("PARENT#" + PARENT, "CHILD#" + STUDENT) not in world.table.items


@pytest.mark.parametrize("deleting", [PARENT, STUDENT], ids=["parent", "student"])
def test_self_service_request_refuses_either_deletion_pending_account(
    world: RelationshipWorld, deleting: str
) -> None:
    world.table.seed_account_fence(deleting, status="deletion_pending", generation=2)

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.request_link(
            requester_id=PARENT, counterpart_id=STUDENT, now=NOW
        )


def test_confirmation_refuses_a_fence_that_closed_after_the_request(
    world: RelationshipWorld,
) -> None:
    """The interleaving: admission was fine, the commit is not."""
    parent_link_service.request_link(requester_id=PARENT, counterpart_id=STUDENT, now=NOW)
    world.table.seed_account_fence(STUDENT, status="deletion_pending", generation=2)

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        parent_link_service.confirm_link(
            parent_id=PARENT, student_id=STUDENT, actor_id=STUDENT, now=NOW
        )

    assert world.table.items[("PARENT#" + PARENT, "CHILD#" + STUDENT)]["status"] == "pending"


def test_the_fence_condition_travels_with_the_relationship_write(
    world: RelationshipWorld,
) -> None:
    """The refusal above must come from the transaction, not only from a pre-read."""
    world.link(PARENT, STUDENT)

    checked = {
        operation["ConditionCheck"]["Key"]["PK"]
        for transaction in world.table.transactions
        for operation in transaction
        if "ConditionCheck" in operation
    }

    assert checked == {f"USER#{PARENT}", f"USER#{STUDENT}"}


# ---------------------------------------------------------------------------
# Issue #4: the account-profile deletion branch owns the new link rows
# ---------------------------------------------------------------------------


class _DeletionTable:
    """Base-table scan plus the row-delete hook the branch reaches for."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = {(item["PK"], item["SK"]): dict(item) for item in items}

    def scan(self, **_kwargs: object) -> dict[str, Any]:
        return {"Items": [dict(item) for item in self.items.values()]}

    def delete_owned_row(self, item: dict[str, Any], _user_id: str, _generation: int) -> None:
        self.items.pop((item["PK"], item["SK"]), None)


def _link_rows(parent_id: str, student_id: str) -> list[dict[str, Any]]:
    body = {
        "entity_type": "parent_student_link",
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": "child",
        "status": "active",
        "initiator_role": "admin",
        "created_by": "admin-1",
        "linked_at": NOW,
        "updated_by": "admin-1",
        "link_updated_at": NOW,
    }
    return [
        {"PK": f"PARENT#{parent_id}", "SK": f"CHILD#{student_id}", **body},
        {"PK": f"STUDENT#{student_id}", "SK": f"PARENT#{parent_id}", **body},
    ]


def _run_profile_branch(table: _DeletionTable, user_id: str, passes: int) -> Any:
    command = {"user_id": user_id, "generation": 7}
    previous: dict[str, Any] = {}
    result = None
    for _ in range(passes):
        result = account_deletion_service._account_profile_branch(
            command=command, previous=previous
        )
        previous = {
            "cursor": result.cursor,
            "debt_counts": result.debt_counts,
            "epoch": result.epoch,
        }
    return result


def test_account_profile_deletion_completes_when_nothing_is_owed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: the branch must still be able to finish."""
    table = _DeletionTable([])
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)

    result = _run_profile_branch(table, PARENT, passes=2)

    assert result.status == "complete" and result.quiescent is True


@pytest.mark.parametrize("deleting", [PARENT, STUDENT], ids=["parent", "student"])
def test_account_profile_deletion_cannot_finish_with_active_new_links(
    monkeypatch: pytest.MonkeyPatch, deleting: str
) -> None:
    table = _DeletionTable(_link_rows(PARENT, STUDENT))
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)

    result = _run_profile_branch(table, deleting, passes=2)

    assert result.status != "complete"
    assert result.quiescent is False
    assert table.items == {}


@pytest.mark.parametrize("deleting", [PARENT, STUDENT], ids=["parent", "student"])
def test_account_profile_deletion_removes_both_link_directions(
    monkeypatch: pytest.MonkeyPatch, deleting: str
) -> None:
    table = _DeletionTable(_link_rows(PARENT, STUDENT))
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)

    _run_profile_branch(table, deleting, passes=1)

    assert table.items == {}


# ---------------------------------------------------------------------------
# Issue #3, the generation path: the recipient is judged again at the last step
# ---------------------------------------------------------------------------


class _GenerationDelivery:
    """Everything `store_and_send_weekly_report` touches except the judge."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.sent: list[str] = []
        self.status_updates: list[tuple[str, dict[str, Any]]] = []
        # The repository module is shared; link writes pass their own table and
        # must still see the real fence.
        real_fence = account_deletion_repo.require_active_account_fence
        monkeypatch.setattr(
            report_service.account_deletion_repo,
            "require_active_account_fence",
            lambda owner, **kwargs: (
                real_fence(owner, **kwargs) if kwargs else {"status": "active", "generation": 7}
            ),
        )
        monkeypatch.setattr(
            report_service.report_artifact_service,
            "write_fenced_report_artifacts",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr(report_service.report_repo, "put_report", lambda _item: None)
        monkeypatch.setattr(
            report_service.report_repo,
            "update_report_status",
            lambda _report_id, status, **fields: self.status_updates.append((status, fields)),
        )
        monkeypatch.setattr(
            report_service.notify_service,
            "send_fenced_weekly_report_email",
            lambda email, _html, **_kwargs: (self.sent.append(email), "accepted")[1],
        )


@pytest.fixture
def delivery(monkeypatch: pytest.MonkeyPatch) -> _GenerationDelivery:
    return _GenerationDelivery(monkeypatch)


def _generate_and_store(world: RelationshipWorld, change=None) -> dict[str, Any]:
    """Build the payload while the relationship holds, change the world, deliver."""
    payload = report_service.build_weekly_learning_payload(PARENT, STUDENT, "2026-06-01")
    assert payload["parent"]["email"] == f"{PARENT}@stoa.test"
    if change is not None:
        change()
    return report_service.store_and_send_weekly_report(
        payload,
        report_service.build_deterministic_report_fallback(payload),
    )


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_current_parent_still_receives_the_generated_report(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    """Negative control for the refusals below."""
    world.bind(PARENT, STUDENT)

    stored = _generate_and_store(world)

    assert delivery.sent == [f"{PARENT}@stoa.test"]
    assert stored["status"] == "email_sent"
    assert stored["email_status"] == "sent"


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_new_link_parent_receives_the_generated_report(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    world.link(PARENT, STUDENT)

    stored = _generate_and_store(world)

    assert delivery.sent == [f"{PARENT}@stoa.test"]
    assert stored["email_status"] == "sent"


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_parent_revoked_after_the_payload_does_not_receive_the_report(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    world.bind(PARENT, STUDENT)

    stored = _generate_and_store(world, lambda: world.revoke_binding(PARENT, STUDENT))

    assert delivery.sent == []
    assert stored["status"] == "email_failed"
    assert stored["email_status"] == "failed"
    assert stored["email_error_class"] == "relationship_revoked"
    assert delivery.status_updates[-1][0] == "email_failed"
    assert delivery.status_updates[-1][1]["email_error_class"] == "relationship_revoked"


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_parent_whose_account_closes_after_the_payload_does_not_receive_the_report(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    world.bind(PARENT, STUDENT)

    def close_parent() -> None:
        world.profiles[PARENT]["account_status"] = "deletion_pending"

    stored = _generate_and_store(world, close_parent)

    assert delivery.sent == []
    assert stored["email_error_class"] == "relationship_revoked"


@pytest.mark.usefixtures("quiet_report_sources")
def test_the_generated_report_goes_to_the_parents_current_address(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    world.bind(PARENT, STUDENT)

    def change_address() -> None:
        world.profiles[PARENT]["email"] = "new-address@stoa.test"

    stored = _generate_and_store(world, change_address)

    assert delivery.sent == ["new-address@stoa.test"]
    assert stored["email_status"] == "sent"


@pytest.mark.usefixtures("quiet_report_sources")
def test_a_parent_without_an_address_is_not_sent_the_generated_report(
    world: RelationshipWorld, delivery: _GenerationDelivery
) -> None:
    world.bind(PARENT, STUDENT)

    def drop_address() -> None:
        world.profiles[PARENT]["email"] = "  "

    stored = _generate_and_store(world, drop_address)

    assert delivery.sent == []
    assert stored["status"] == "email_failed"
    assert stored["email_error_class"] == "recipient_missing"


def test_the_recipient_judge_tells_its_three_answers_apart(world: RelationshipWorld) -> None:
    assert parent_link_service.current_parent_recipient(PARENT, STUDENT) == (
        parent_link_service.ParentRecipient(refusal="relationship_revoked")
    )
    world.bind(PARENT, STUDENT)
    assert parent_link_service.current_parent_recipient(PARENT, STUDENT) == (
        parent_link_service.ParentRecipient(email=f"{PARENT}@stoa.test")
    )
    world.profiles[PARENT].pop("email")
    assert parent_link_service.current_parent_recipient(PARENT, STUDENT) == (
        parent_link_service.ParentRecipient(refusal="recipient_missing")
    )


def test_a_resend_to_a_current_parent_without_an_address_is_refused_as_such(
    world: RelationshipWorld, resend_doubles: list[tuple[str, str]]
) -> None:
    world.bind(PARENT, STUDENT)
    world.profiles[PARENT]["email"] = ""

    with pytest.raises(report_recovery_service.ReportRecoveryError) as refused:
        report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert refused.value.status_code == 422
    assert refused.value.error_class == "recipient_missing"
    assert resend_doubles == []


def test_a_resend_does_not_need_the_archived_address(
    world: RelationshipWorld, resend_doubles: list[tuple[str, str]]
) -> None:
    world.bind(PARENT, STUDENT)
    report = _failed_report()
    report.pop("parent_email")

    result = report_recovery_service.resend_report_email(report, operator="admin-1")

    assert result.status == "email_sent"
    assert resend_doubles == [(f"{PARENT}@stoa.test", "<html>Report</html>")]


# ---------------------------------------------------------------------------
# Card 022 B-2: the entitlement list judges children the same way
# ---------------------------------------------------------------------------


@pytest.fixture
def entitlement_list(monkeypatch: pytest.MonkeyPatch):
    """The parent's entitlement list, with each child's plan lookup stubbed out."""
    monkeypatch.setattr(
        entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, **_k: {"studentId": student_id, "parentId": PARENT},
    )

    def listed() -> list[str]:
        return [
            item["studentId"]
            for item in entitlement_service.list_parent_child_entitlements(
                PARENT, settings=Settings()
            )
        ]

    return listed


def test_a_reverse_revoked_legacy_binding_leaves_the_entitlement_list(
    world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch, entitlement_list
) -> None:
    """The forward row still says active; the reverse row has been revoked."""
    world.bind(PARENT, STUDENT)
    revoked_reverse = {**world.bindings[(PARENT, STUDENT)], "status": "revoked"}
    monkeypatch.setattr(
        user_repo,
        "get_student_parent_binding",
        lambda student_id, parent_id: (
            deepcopy(revoked_reverse) if (parent_id, student_id) == (PARENT, STUDENT) else None
        ),
    )

    assert parent_link_service.current_relationship(PARENT, STUDENT) is None
    assert entitlement_list() == []


def test_a_current_legacy_binding_is_on_the_entitlement_list(
    world: RelationshipWorld, entitlement_list
) -> None:
    world.bind(PARENT, STUDENT)

    assert entitlement_list() == [STUDENT]


def test_a_current_new_link_is_on_the_entitlement_list(
    world: RelationshipWorld, entitlement_list
) -> None:
    world.link(PARENT, STUDENT)

    assert entitlement_list() == [STUDENT]
