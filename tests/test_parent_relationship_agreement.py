"""#34 / #85 / #208: every place that decides "may this parent see this child" agrees.

Since #208 there is one judge, `current_relationship`, and only link rows are a
relationship. The authorization engine, the parent's children list and the
judge's own listing all ask it, so they cannot disagree about whether a given
relationship lets the parent in - and the retired legacy shape (binding rows,
a profile's `parent_id`) lets nobody in. Every state below is put to all four
readers, and the expected verdict is written down once.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

import pytest

from stoa.db.repositories import parent_link_repo, user_repo
from stoa.routers import parents
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPurpose,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
)
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import current_relationship, parent_link_service
from stoa.services.current_relationship import Standing

from test_parent_relationship_current import NOW, PARENT, STUDENT, RelationshipWorld


def _tamper_link_side(world: RelationshipWorld, key: dict[str, str], **fields: object) -> None:
    world.table.items[(key["PK"], key["SK"])].update(fields)


def _link(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)


def _link_pending(world: RelationshipWorld) -> None:
    parent_link_service.request_link(requester_id=PARENT, counterpart_id=STUDENT, now=NOW)


def _link_rejected(world: RelationshipWorld) -> None:
    parent_link_service.request_link(requester_id=PARENT, counterpart_id=STUDENT, now=NOW)
    parent_link_service.reject_link(
        parent_id=PARENT, student_id=STUDENT, actor_id=STUDENT, now=NOW
    )


def _link_revoked(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    world.revoke(PARENT, STUDENT)


def _link_sides_disagree(world: RelationshipWorld) -> None:
    # No writer leaves the two sides in different statuses; a repair or a
    # restore could. Only the student side has moved off active.
    world.link(PARENT, STUDENT)
    _tamper_link_side(
        world, parent_link_repo.student_side_key(STUDENT, PARENT), status="rejected"
    )


def _link_versions_disagree(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    _tamper_link_side(
        world,
        parent_link_repo.student_side_key(STUDENT, PARENT),
        link_updated_at="2026-09-19T11:00:00+00:00",
    )


def _link_one_side_only(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    key = parent_link_repo.student_side_key(STUDENT, PARENT)
    world.table.items.pop((key["PK"], key["SK"]))


def _link_parent_suspended(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[PARENT]["account_status"] = "suspended"


def _link_student_suspended(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[STUDENT]["account_status"] = "suspended"


def _link_student_wrong_role(world: RelationshipWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[STUDENT]["role"] = "teacher"


def _legacy_binding(world: RelationshipWorld) -> None:
    world.legacy_bind(PARENT, STUDENT)


def _profile_only(world: RelationshipWorld) -> None:
    world.strand_profile_only(PARENT, STUDENT)


def _legacy_binding_and_pending_link(world: RelationshipWorld) -> None:
    world.legacy_bind(PARENT, STUDENT)
    _link_pending(world)


def _revoked_legacy_binding_and_active_link(world: RelationshipWorld) -> None:
    world.legacy_bind(PARENT, STUDENT, status="revoked")
    world.link(PARENT, STUDENT)


def _nothing(world: RelationshipWorld) -> None:
    return None


# (name, arrange, allowed, the judge's standing)
STATES: list[tuple[str, Callable[[RelationshipWorld], None], bool, Standing]] = [
    ("link active both ways", _link, True, Standing.CURRENT),
    ("link pending", _link_pending, False, Standing.KNOWN),
    ("link rejected", _link_rejected, False, Standing.KNOWN),
    ("link revoked", _link_revoked, False, Standing.KNOWN),
    ("link sides disagree on status", _link_sides_disagree, False, Standing.KNOWN),
    ("link sides disagree on version", _link_versions_disagree, False, Standing.KNOWN),
    ("link stored on one side only", _link_one_side_only, False, Standing.UNKNOWN),
    ("link, parent suspended", _link_parent_suspended, False, Standing.KNOWN),
    ("link, student suspended", _link_student_suspended, False, Standing.KNOWN),
    ("link, student is not a student", _link_student_wrong_role, False, Standing.KNOWN),
    ("legacy binding active both ways", _legacy_binding, False, Standing.UNKNOWN),
    ("only the profile names the parent", _profile_only, False, Standing.UNKNOWN),
    (
        "legacy binding active, link pending",
        _legacy_binding_and_pending_link,
        False,
        Standing.KNOWN,
    ),
    (
        "legacy binding revoked, link active",
        _revoked_legacy_binding_and_active_link,
        True,
        Standing.CURRENT,
    ),
    ("no relationship at all", _nothing, False, Standing.UNKNOWN),
]


def _engine_facts(parent_id: str, student_id: str) -> AuthorizationFacts:
    actor = Actor(
        parent_id,
        "https://identity.test",
        f"{parent_id}-subject",
        CanonicalRole.PARENT,
        AccountStatus.ACTIVE,
        "parent",
    )
    return asyncio.run(
        CurrentAuthorizationFactRepository().facts_for(
            actor,
            ResourceRef(ResourceType.STUDENT, student_id, student_id),
            AuthorizationAction.READ,
            AuthorizationPurpose.PARENT_OVERSIGHT,
            {},
        )
    )


def _verdicts(parent_id: str, student_id: str) -> dict[str, bool]:
    facts = _engine_facts(parent_id, student_id)
    return {
        "authorization engine": facts.parent is not None
        and facts.parent.matches(parent_id, student_id),
        "children list": any(
            child.get("user_id") == student_id
            for child in parents._list_children_for_parent(parent_id)
        ),
        "judge": current_relationship.judge(parent_id, student_id).is_current,
        "children_of": any(
            verdict.student_id == student_id
            for verdict in current_relationship.children_of(parent_id)
        ),
    }


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> RelationshipWorld:
    built = RelationshipWorld()
    built.account(PARENT, "parent")
    built.account(STUDENT, "student")
    return built.install(monkeypatch)


@pytest.mark.parametrize(
    ("arrange", "allowed"),
    [pytest.param(arrange, allowed, id=name) for name, arrange, allowed, _ in STATES],
)
def test_every_reader_gives_the_same_verdict(
    world: RelationshipWorld, arrange: Callable[[RelationshipWorld], None], allowed: bool
) -> None:
    arrange(world)
    verdicts = _verdicts(PARENT, STUDENT)
    assert verdicts == dict.fromkeys(verdicts, allowed)


@pytest.mark.parametrize(
    ("arrange", "standing"),
    [pytest.param(arrange, standing, id=name) for name, arrange, _, standing in STATES],
)
def test_the_engine_refuses_what_the_judge_knows_and_hides_what_it_does_not(
    world: RelationshipWorld,
    arrange: Callable[[RelationshipWorld], None],
    standing: Standing,
) -> None:
    arrange(world)

    facts = _engine_facts(PARENT, STUDENT)

    assert facts.parent is not None and facts.parent.verdict is not None
    assert facts.parent.verdict.standing is standing
    assert facts.parent.known_to(PARENT, STUDENT) is (standing is not Standing.UNKNOWN)


def test_the_states_include_both_verdicts() -> None:
    # A table that only ever expects "refused" would pass a change that refuses
    # everyone; it has to show a parent being let in as well.
    allowed = {name for name, _arrange, verdict, _ in STATES if verdict}
    assert "link active both ways" in allowed
    assert len(allowed) < len(STATES)


class ProfileStoreDown(RuntimeError):
    pass


def _student_profile_unreadable(world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = world.profiles

    def get_user(user_id: str, **_kwargs: object) -> dict | None:
        if user_id == STUDENT:
            raise ProfileStoreDown("student profile unavailable")
        return deepcopy(profiles.get(user_id))

    monkeypatch.setattr(user_repo, "get_user", get_user)


@pytest.mark.parametrize(
    "arrange",
    [
        pytest.param(_link_revoked, id="link revoked"),
        pytest.param(_link_sides_disagree, id="link sides disagree"),
        pytest.param(_link_parent_suspended, id="parent suspended"),
    ],
)
def test_a_refused_link_never_reads_the_student_profile(
    world: RelationshipWorld,
    monkeypatch: pytest.MonkeyPatch,
    arrange: Callable[[RelationshipWorld], None],
) -> None:
    # Refused on its rows or on its parent, a pair must stay refused even when
    # the student's profile cannot be read: the judge stops before that read,
    # and one that reads it first turns a refusal into an error (#85).
    arrange(world)
    _student_profile_unreadable(world, monkeypatch)

    assert current_relationship.judge(PARENT, STUDENT).is_current is False


def test_a_valid_link_still_needs_the_student_profile(
    world: RelationshipWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other side of the test above: a pair that would be allowed does
    # reach the student's profile, so a failure there is not silently a "no".
    _link(world)
    _student_profile_unreadable(world, monkeypatch)

    with pytest.raises(ProfileStoreDown):
        current_relationship.judge(PARENT, STUDENT)
