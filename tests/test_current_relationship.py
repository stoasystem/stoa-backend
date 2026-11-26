"""The one judge of the current parent-student relationship (#208, #287)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from fakes.links import LINKED_AT as STAMP, LinkRows
from stoa.db.repositories import parent_link_repo
from stoa.services import current_relationship
from stoa.services.current_relationship import Standing


LATER = "2026-11-07T09:00:00+00:00"


@pytest.fixture
def world(link_rows: LinkRows) -> LinkRows:
    """The shared link-row fixture, with the accounts these tests name."""
    built = link_rows
    built.account("parent-1", "parent")
    built.account("parent-2", "parent")
    built.account("student-1", "student")
    built.account("student-2", "student")
    built.account("student-3", "student")
    return built


def _legacy_binding_only(world: LinkRows) -> None:
    """The retired shape: binding rows and a profile pointer, no link (#208)."""
    for pk, sk in (("USER#parent-1", "CHILD#student-1"), ("USER#student-1", "PARENT#parent-1")):
        world.table.seed(
            {
                "PK": pk,
                "SK": sk,
                "entity_type": "parent_student_binding",
                "parent_id": "parent-1",
                "student_id": "student-1",
                "relationship": "child",
                "status": "active",
                "version": 1,
            }
        )
    world.account(
        "student-1", "student", parent_id="parent-1", parent_binding_status="active"
    )


JUDGE_CASES: list[tuple[str, Callable[[LinkRows], None], Standing]] = [
    ("both sides active, both accounts usable", lambda w: w.link("parent-1", "student-1"), Standing.CURRENT),
    ("pending request", lambda w: w.link("parent-1", "student-1", status="pending"), Standing.KNOWN),
    ("rejected or revoked", lambda w: w.link("parent-1", "student-1", status="rejected"), Standing.KNOWN),
    (
        "sides disagree on status",
        lambda w: w.link("parent-1", "student-1", student_side_status="rejected"),
        Standing.KNOWN,
    ),
    (
        "sides disagree on version",
        lambda w: w.link("parent-1", "student-1", student_side_stamp=LATER),
        Standing.KNOWN,
    ),
    (
        "parent account suspended",
        lambda w: (w.link("parent-1", "student-1"), w.account("parent-1", "parent", status="suspended")),
        Standing.KNOWN,
    ),
    (
        "student account suspended",
        lambda w: (w.link("parent-1", "student-1"), w.account("student-1", "student", status="suspended")),
        Standing.KNOWN,
    ),
    (
        "parent account holds another role",
        lambda w: (w.link("parent-1", "student-1"), w.account("parent-1", "teacher")),
        Standing.KNOWN,
    ),
    (
        "student profile missing",
        lambda w: (w.link("parent-1", "student-1"), w.table.rows.pop(("USER#student-1", "PROFILE"))),
        Standing.KNOWN,
    ),
    ("only the parent's side stored", lambda w: w.link("parent-1", "student-1", only_parent_side=True), Standing.UNKNOWN),
    ("nothing stored", lambda w: None, Standing.UNKNOWN),
    ("legacy binding rows and profile pointer only", _legacy_binding_only, Standing.UNKNOWN),
]


@pytest.mark.parametrize(
    ("arrange", "standing"),
    [(arrange, standing) for _, arrange, standing in JUDGE_CASES],
    ids=[name for name, _, _ in JUDGE_CASES],
)
def test_judge_answers_one_of_three_states(world, arrange, standing):
    arrange(world)

    verdict = current_relationship.judge("parent-1", "student-1", table=world.table)

    assert verdict.standing is standing
    assert verdict.about("parent-1", "student-1")
    assert verdict.is_current is (standing is Standing.CURRENT)
    assert verdict.is_known is (standing is not Standing.UNKNOWN)


def test_a_current_verdict_carries_its_source_and_row_version(world):
    world.link("parent-1", "student-1", relationship="child")

    verdict = current_relationship.judge("parent-1", "student-1", table=world.table)

    assert verdict.source == current_relationship.SOURCE_LINK == "parent_student_link"
    assert verdict.version == STAMP
    assert verdict.relationship == "child"
    assert verdict.status == "active"


@pytest.mark.parametrize(("parent_id", "student_id"), [("", "student-1"), ("parent-1", "")])
def test_a_blank_party_is_unknown_without_reading(world, parent_id, student_id):
    world.link("parent-1", "student-1")

    verdict = current_relationship.judge(parent_id, student_id, table=world.table)

    assert verdict.standing is Standing.UNKNOWN
    assert world.table.calls["get_item"] == 0


def test_rows_refused_never_read_a_profile(world):
    """#85: a pair refused on its rows cannot be turned into an error by a profile read."""
    world.link("parent-1", "student-1", status="pending")

    current_relationship.judge("parent-1", "student-1", table=world.table)

    profile_reads = [
        request
        for operation, request in world.table.requests
        if operation == "get_item" and request["Key"]["SK"] == "PROFILE"
    ]
    assert profile_reads == []


def test_children_of_lists_only_current_relationships(world):
    world.link("parent-1", "student-1")
    world.link("parent-1", "student-2", status="pending")
    world.link("parent-1", "student-3")
    world.account("student-3", "student", status="suspended")

    children = current_relationship.children_of("parent-1", table=world.table)

    assert [verdict.student_id for verdict in children] == ["student-1"]
    assert all(verdict.is_current for verdict in children)


def test_children_of_does_not_judge_a_side_that_is_not_active(world):
    world.link("parent-1", "student-2", status="pending")
    world.link("parent-1", "student-3", status="rejected")

    assert current_relationship.children_of("parent-1", table=world.table) == []
    assert current_relationship.parents_of("student-2", table=world.table) == []
    assert world.table.calls["get_item"] == 0


def test_known_children_of_shows_what_is_not_current_too(world):
    world.link("parent-1", "student-1")
    world.link("parent-1", "student-2", status="pending")
    world.link("parent-1", "student-3")
    world.account("student-3", "student", status="suspended")

    known = current_relationship.known_children_of("parent-1", table=world.table)

    assert {(verdict.student_id, verdict.standing) for verdict in known} == {
        ("student-1", Standing.CURRENT),
        ("student-2", Standing.KNOWN),
        ("student-3", Standing.KNOWN),
    }


def test_parents_of_lists_only_current_relationships(world):
    world.link("parent-1", "student-1")
    world.link("parent-2", "student-1", status="rejected")

    parents = current_relationship.parents_of("student-1", table=world.table)

    assert [verdict.parent_id for verdict in parents] == ["parent-1"]


def test_listings_ignore_the_legacy_shape(world):
    _legacy_binding_only(world)

    assert current_relationship.children_of("parent-1", table=world.table) == []
    assert current_relationship.parents_of("student-1", table=world.table) == []


def test_candidate_pairs_read_every_page_for_active_parent_sides(world):
    world.table.page_item_cap = 2
    world.account("parent-3", "parent")
    world.account("parent-4", "parent")
    world.link("parent-1", "student-1")
    world.link("parent-1", "student-2", status="pending")
    world.link("parent-2", "student-3")
    world.link("parent-4", "student-2")
    _legacy_binding_only(world)

    pairs = current_relationship.candidate_pairs(table=world.table)

    assert sorted(pairs) == [
        ("parent-1", "student-1"),
        ("parent-2", "student-3"),
        ("parent-4", "student-2"),
    ]
    # Card 135: the parents from the account listing, then their own rows.
    assert world.table.calls["scan"] == 0
    assert world.table.calls["query"] > 1


def _scanned_candidates(world: LinkRows) -> set[tuple[str, str]]:
    """What the whole-table scan `candidate_pairs` replaced found, row by row."""
    return {
        (row["parent_id"], row["student_id"])
        for row in world.table.rows.values()
        if row.get("entity_type") == parent_link_repo.ENTITY_TYPE
        and row.get("status") == parent_link_repo.STATUS_ACTIVE
        and str(row.get("SK") or "").startswith("CHILD#")
        and isinstance(row.get("parent_id"), str)
        and isinstance(row.get("student_id"), str)
    }


def test_candidate_pairs_keep_every_pair_the_scan_found_that_can_be_current(world):
    """Card 135: the listing read gives the weekly job the same families.

    Every pair the old scan found and the judge holds current is found, and
    nothing is found that the scan did not: a pair missed is a parent's report
    not sent, a pair added is a report sent to someone else's parent.
    """
    world.table.page_item_cap = 3
    for index in range(5, 12):
        world.account(f"parent-{index}", "parent")
        world.account(f"student-{index}", "student")
        world.link(f"parent-{index}", f"student-{index}")
    world.link("parent-5", "student-6")
    world.link("parent-1", "student-1")
    world.link("parent-1", "student-2", status="rejected")
    world.link("parent-2", "student-3", only_parent_side=True)
    world.link("parent-2", "student-1", student_side_status="pending")
    # A suspended parent and one whose account holds another role: found by the
    # scan, never current.
    world.account("parent-6", "parent", status="suspended")
    world.account("parent-7", "teacher")
    # A student-side row alone, as the scan never read it.
    world.table.seed(
        {
            **parent_link_repo.student_side_key("student-8", "parent-9"),
            "entity_type": parent_link_repo.ENTITY_TYPE,
            "parent_id": "parent-9",
            "student_id": "student-8",
            "status": parent_link_repo.STATUS_ACTIVE,
        }
    )
    _legacy_binding_only(world)

    found = current_relationship.candidate_pairs(table=world.table)
    scanned = _scanned_candidates(world)

    assert len(found) == len(set(found))
    assert set(found) <= scanned

    def current(pairs):
        return {
            pair
            for pair in pairs
            if current_relationship.judge(*pair, table=world.table).is_current
        }

    assert current(found) == current(scanned)
    assert len(current(found)) == 7
    # The suspended parent is still a candidate, judged and refused by the job.
    assert ("parent-6", "student-6") in found
    assert world.table.calls["scan"] == 0


# --- Many at once (card 133) ----------------------------------------------------
#
# The batched entries must answer exactly what `judge`, `children_of` and
# `parents_of` answer, pair by pair, over the same rows. Each comparison below
# arranges one table and asks both.


def _families(world: LinkRows) -> None:
    """Every kind of pair at once, several sharing a parent or a student."""
    for user_id, role in (
        ("parent-3", "parent"),
        ("parent-4", "teacher"),
        ("student-4", "student"),
        ("student-5", "student"),
    ):
        world.account(user_id, role)
    world.link("parent-1", "student-1")
    world.link("parent-1", "student-2", status="pending")
    world.link("parent-1", "student-3")
    world.account("student-3", "student", status="suspended")
    world.link("parent-2", "student-1", student_side_status="rejected")
    world.link("parent-2", "student-2", student_side_stamp=LATER)
    world.link("parent-2", "student-3", only_parent_side=True)
    world.link("parent-2", "student-4")
    # The parent's account is gone; the rows are not.
    world.link("parent-3", "student-1")
    world.table.rows.pop(("USER#parent-3", "PROFILE"))
    # The student's profile is a deletion tombstone.
    world.link("parent-1", "student-5")
    world.table.rows[("USER#student-5", "PROFILE")] = {
        "PK": "USER#student-5",
        "SK": "PROFILE",
        "entity_type": "private_row_deletion_tombstone",
        "status": "deleted",
        "owner_deletion_generation": 1,
    }
    world.link("parent-4", "student-2")
    world.link("parent-4", "student-4", status="rejected")
    world.link("parent-3", "student-4")


PARENTS = ("parent-1", "parent-2", "parent-3", "parent-4")
STUDENTS = ("student-1", "student-2", "student-3", "student-4", "student-5")


@pytest.mark.parametrize(
    "arrange", [arrange for _, arrange, _ in JUDGE_CASES], ids=[name for name, _, _ in JUDGE_CASES]
)
def test_judge_many_answers_what_judge_answers_for_each_case(world, arrange):
    arrange(world)

    batched = current_relationship.judge_many([("parent-1", "student-1")], table=world.table)

    assert batched == {
        ("parent-1", "student-1"): current_relationship.judge(
            "parent-1", "student-1", table=world.table
        )
    }


def test_judge_many_answers_what_judge_answers_for_every_pair_at_once(world):
    _families(world)
    pairs = [
        (parent_id, student_id)
        for parent_id in (*PARENTS, "parent-9", "")
        for student_id in (*STUDENTS, "student-9", "")
    ]
    world.table.calls.clear()

    batched = current_relationship.judge_many(pairs, table=world.table)

    assert world.table.calls["get_item"] == 0
    assert world.table.calls["batch_get_item"] == 1
    one_by_one = {
        pair: current_relationship.judge(*pair, table=world.table) for pair in pairs
    }
    assert batched == one_by_one
    assert {verdict.standing for verdict in batched.values()} == set(Standing)


@pytest.mark.parametrize("pair", [(" ", "student-1"), ("parent-1", " ")])
def test_judge_many_refuses_a_blank_id_as_judge_does(world, pair):
    with pytest.raises(ValueError):
        current_relationship.judge(*pair, table=world.table)
    with pytest.raises(ValueError):
        current_relationship.judge_many([pair], table=world.table)


def test_current_relationships_of_answers_children_of_and_parents_of(world):
    _families(world)
    world.table.calls.clear()

    batched = current_relationship.current_relationships_of(
        parent_ids=[*PARENTS, "parent-9", ""], student_ids=[*STUDENTS, "student-9"],
        table=world.table,
    )

    assert world.table.calls["get_item"] == 0
    assert world.table.calls["batch_get_item"] == 1
    assert batched.children == {
        parent_id: current_relationship.children_of(parent_id, table=world.table)
        for parent_id in (*PARENTS, "parent-9")
    }
    assert batched.parents == {
        student_id: current_relationship.parents_of(student_id, table=world.table)
        for student_id in (*STUDENTS, "student-9")
    }
    assert [verdict.student_id for verdict in batched.children["parent-1"]] == ["student-1"]
    assert [verdict.parent_id for verdict in batched.parents["student-4"]] == ["parent-2"]


def test_current_relationships_of_hands_back_the_profiles_it_read(world):
    world.link("parent-1", "student-1")
    world.account("student-1", "student", account_number="S26-0001")

    batched = current_relationship.current_relationships_of(
        parent_ids=["parent-1"], table=world.table
    )

    assert batched.profiles["student-1"]["account_number"] == "S26-0001"
    assert set(batched.profiles) == {"parent-1", "student-1"}


def test_current_relationships_of_with_nobody_reads_nothing(world):
    batched = current_relationship.current_relationships_of(table=world.table)

    assert batched == current_relationship.CurrentRelationships({}, {}, {})
    assert dict(world.table.calls) == {}


# --- Revoking -----------------------------------------------------------------


def _both_sides(world: LinkRows) -> list[dict[str, Any] | None]:
    return [
        world.side("PARENT#parent-1", "CHILD#student-1"),
        world.side("STUDENT#student-1", "PARENT#parent-1"),
    ]


REVOKE_CASES: list[tuple[str, Callable[[LinkRows], None]]] = [
    ("a current relationship", lambda w: w.link("parent-1", "student-1")),
    (
        "an active link whose student account is suspended",
        lambda w: (w.link("parent-1", "student-1"), w.account("student-1", "student", status="suspended")),
    ),
    (
        "an active link whose parent is being deleted",
        lambda w: (
            w.link("parent-1", "student-1"),
            w.account("parent-1", "parent", status="deletion_pending"),
            w.table.seed(
                {
                    "PK": "USER#parent-1",
                    "SK": "ACCOUNT_FENCE",
                    "entity_type": "account_fence",
                    "status": "closed",
                    "generation": 2,
                }
            ),
        ),
    ),
    ("sides that disagree", lambda w: w.link("parent-1", "student-1", student_side_status="rejected")),
    ("an active parent side with no mirror", lambda w: w.link("parent-1", "student-1", only_parent_side=True)),
]


@pytest.mark.parametrize(
    "arrange",
    [arrange for _, arrange in REVOKE_CASES],
    ids=[name for name, _ in REVOKE_CASES],
)
def test_revoke_closes_both_sides_in_one_transaction(world, arrange):
    arrange(world)

    closed = current_relationship.revoke(
        "parent-1", "student-1", actor_id="admin-9", now=LATER, table=world.table
    )

    assert closed is not None and closed.standing is Standing.KNOWN
    assert closed.version == LATER
    for side in _both_sides(world):
        assert side is not None
        assert side["status"] == parent_link_repo.STATUS_REJECTED
        assert side["link_updated_at"] == LATER
        assert side["updated_by"] == "admin-9"
    assert world.table.calls["transact_write_items"] == 1
    verdict = current_relationship.judge("parent-1", "student-1", table=world.table)
    assert verdict.standing is Standing.KNOWN


NOTHING_TO_REVOKE: list[tuple[str, Callable[[LinkRows], None]]] = [
    ("nothing stored", lambda w: None),
    ("a pending request", lambda w: w.link("parent-1", "student-1", status="pending")),
    ("an already closed link", lambda w: w.link("parent-1", "student-1", status="rejected")),
    ("the legacy shape", _legacy_binding_only),
]


@pytest.mark.parametrize(
    "arrange",
    [arrange for _, arrange in NOTHING_TO_REVOKE],
    ids=[name for name, _ in NOTHING_TO_REVOKE],
)
def test_revoke_without_an_open_link_writes_nothing(world, arrange):
    arrange(world)
    before = dict(world.table.rows)

    closed = current_relationship.revoke(
        "parent-1", "student-1", actor_id="admin-9", now=LATER, table=world.table
    )

    assert closed is None
    assert world.table.rows == before
    assert world.table.calls["transact_write_items"] == 0


def test_a_racer_on_either_side_refuses_the_whole_revoke(world, monkeypatch):
    world.link("parent-1", "student-1")
    real_read = parent_link_repo.get_student_side_link

    def read_then_race(student_id, parent_id, *, table=None):
        side = real_read(student_id, parent_id, table=table)
        # Someone rewrites the student's side after it was read.
        world.side(f"STUDENT#{student_id}", f"PARENT#{parent_id}")[
            "link_updated_at"
        ] = "2026-11-05T00:00:00+00:00"
        return side

    monkeypatch.setattr(parent_link_repo, "get_student_side_link", read_then_race)

    with pytest.raises(parent_link_repo.ParentLinkConflict):
        current_relationship.revoke(
            "parent-1", "student-1", actor_id="admin-9", now=LATER, table=world.table
        )

    parent_side, student_side = _both_sides(world)
    assert parent_side is not None and parent_side["status"] == "active"
    assert parent_side["link_updated_at"] == STAMP
    assert student_side is not None and student_side["status"] == "active"


def test_revoke_must_advance_the_version(world):
    world.link("parent-1", "student-1")

    with pytest.raises(ValueError):
        current_relationship.revoke(
            "parent-1", "student-1", actor_id="admin-9", now=STAMP, table=world.table
        )

    assert [side["status"] for side in _both_sides(world) if side] == ["active", "active"]
