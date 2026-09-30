"""#34 / #85: the three places that decide "may this parent see this child" agree.

The authorization engine, the parent's children list and `current_relationship`
compose the relationship differently on purpose: the engine reports a known but
inactive link so a party that knows it gets a refusal rather than a 404, the
list survives a link store that cannot answer, and `current_relationship`
raises instead. What they must never do is disagree about whether a given
relationship lets the parent in. Every state below is judged by all four
readers, and the expected verdict is written down once.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

import pytest

from stoa.db.repositories import parent_link_repo, user_repo
from stoa.routers import parents
from stoa.security import authorization
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
)
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import parent_link_service

from test_parent_relationship_current import NOW, PARENT, STUDENT, RelationshipWorld


class AgreementWorld(RelationshipWorld):
    """Adds a reverse binding row that can differ from the forward one."""

    def __init__(self) -> None:
        super().__init__()
        self.reverse_override: dict[tuple[str, str], dict | None] = {}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> AgreementWorld:
        super().install(monkeypatch)

        def reverse(student_id: str, parent_id: str) -> dict | None:
            key = (parent_id, student_id)
            if key in self.reverse_override:
                return deepcopy(self.reverse_override[key])
            return deepcopy(self.bindings.get(key))

        monkeypatch.setattr(user_repo, "get_student_parent_binding", reverse)
        return self

    def tamper_link_side(self, key: dict[str, str], **fields: object) -> None:
        self.table.items[(key["PK"], key["SK"])].update(fields)


def _bind(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)


def _one_sided_binding(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    world.reverse_override[(PARENT, STUDENT)] = None


def _reverse_revoked(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    reverse = deepcopy(world.bindings[(PARENT, STUDENT)])
    reverse["status"] = "revoked"
    world.reverse_override[(PARENT, STUDENT)] = reverse


def _coordinates_disagree(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    reverse = deepcopy(world.bindings[(PARENT, STUDENT)])
    reverse["version"] = 2
    world.reverse_override[(PARENT, STUDENT)] = reverse


def _binding_revoked(world: AgreementWorld) -> None:
    world.revoke_binding(PARENT, STUDENT)


def _profile_only(world: AgreementWorld) -> None:
    world.strand_profile_only(PARENT, STUDENT)


def _binding_parent_suspended(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    world.profiles[PARENT]["account_status"] = "suspended"


def _binding_student_suspended(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    world.profiles[STUDENT]["account_status"] = "suspended"


def _binding_parent_wrong_role(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    world.profiles[PARENT]["role"] = "teacher"


def _link(world: AgreementWorld) -> None:
    world.link(PARENT, STUDENT)


def _link_pending(world: AgreementWorld) -> None:
    parent_link_service.request_link(requester_id=PARENT, counterpart_id=STUDENT, now=NOW)


def _link_rejected(world: AgreementWorld) -> None:
    parent_link_service.request_link(requester_id=PARENT, counterpart_id=STUDENT, now=NOW)
    parent_link_service.reject_link(
        parent_id=PARENT, student_id=STUDENT, actor_id=STUDENT, now=NOW
    )


def _link_sides_disagree(world: AgreementWorld) -> None:
    # No writer leaves the two sides in different statuses; a repair or a
    # restore could. Only the student side has moved off active.
    world.link(PARENT, STUDENT)
    world.tamper_link_side(
        parent_link_repo.student_side_key(STUDENT, PARENT), status="rejected"
    )


def _link_parent_suspended(world: AgreementWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[PARENT]["account_status"] = "suspended"


def _link_student_suspended(world: AgreementWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[STUDENT]["account_status"] = "suspended"


def _link_student_wrong_role(world: AgreementWorld) -> None:
    world.link(PARENT, STUDENT)
    world.profiles[STUDENT]["role"] = "teacher"


def _binding_and_pending_link(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    _link_pending(world)


def _binding_and_rejected_link(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    _link_rejected(world)


def _binding_and_link(world: AgreementWorld) -> None:
    world.bind(PARENT, STUDENT)
    world.link(PARENT, STUDENT)


def _revoked_binding_active_link(world: AgreementWorld) -> None:
    world.revoke_binding(PARENT, STUDENT)
    world.link(PARENT, STUDENT)


def _nothing(world: AgreementWorld) -> None:
    return None


STATES: list[tuple[str, Callable[[AgreementWorld], None], bool]] = [
    ("binding active both ways", _bind, True),
    ("binding with no reverse row", _one_sided_binding, False),
    ("binding whose reverse row is revoked", _reverse_revoked, False),
    ("binding rows that disagree on version", _coordinates_disagree, False),
    ("binding revoked", _binding_revoked, False),
    ("only the profile names the parent", _profile_only, False),
    ("binding, parent suspended", _binding_parent_suspended, False),
    ("binding, student suspended", _binding_student_suspended, False),
    ("binding, parent is not a parent", _binding_parent_wrong_role, False),
    ("link active both ways", _link, True),
    ("link pending", _link_pending, False),
    ("link rejected", _link_rejected, False),
    ("link sides disagree", _link_sides_disagree, False),
    ("link, parent suspended", _link_parent_suspended, False),
    ("link, student suspended", _link_student_suspended, False),
    ("link, student is not a student", _link_student_wrong_role, False),
    ("binding and link both active", _binding_and_link, True),
    ("binding active, link pending", _binding_and_pending_link, True),
    ("binding active, link rejected", _binding_and_rejected_link, True),
    ("binding revoked, link active", _revoked_binding_active_link, True),
    ("no relationship at all", _nothing, False),
]


def _engine(parent_id: str, student_id: str) -> bool:
    actor = Actor(
        parent_id,
        "https://identity.test",
        f"{parent_id}-subject",
        CanonicalRole.PARENT,
        AccountStatus.ACTIVE,
        "parent",
    )
    facts = asyncio.run(
        CurrentAuthorizationFactRepository().facts_for(
            actor,
            ResourceRef(ResourceType.STUDENT, student_id, student_id),
            AuthorizationAction.READ,
            AuthorizationPurpose.PARENT_OVERSIGHT,
            {},
        )
    )
    return facts.parent is not None and facts.parent.matches(parent_id, student_id)


def _verdicts(parent_id: str, student_id: str) -> dict[str, bool]:
    return {
        "authorization engine": _engine(parent_id, student_id),
        "children list": any(
            child.get("user_id") == student_id
            for child in parents._list_children_for_parent(parent_id)
        ),
        "current_relationship": (
            parent_link_service.current_relationship(parent_id, student_id) is not None
        ),
        "current_children": any(
            item.get("student_id") == student_id
            for item in parent_link_service.current_children(parent_id)
        ),
    }


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> AgreementWorld:
    built = AgreementWorld()
    built.account(PARENT, "parent")
    built.account(STUDENT, "student")
    return built.install(monkeypatch)


@pytest.mark.parametrize(
    ("arrange", "allowed"),
    [pytest.param(arrange, allowed, id=name) for name, arrange, allowed in STATES],
)
def test_every_reader_gives_the_same_verdict(
    world: AgreementWorld, arrange: Callable[[AgreementWorld], None], allowed: bool
) -> None:
    arrange(world)
    verdicts = _verdicts(PARENT, STUDENT)
    assert verdicts == dict.fromkeys(verdicts, allowed)


def test_the_states_include_both_verdicts_for_both_key_spaces() -> None:
    # A table that only ever expects "refused" would pass a change that refuses
    # everyone; each key space has to be shown letting a parent in as well.
    allowed = {name for name, _arrange, verdict in STATES if verdict}
    assert "binding active both ways" in allowed
    assert "link active both ways" in allowed
    assert len(allowed) < len(STATES)


def test_a_link_whose_sides_disagree_is_reported_but_never_as_active(
    world: AgreementWorld,
) -> None:
    # The engine reports a link it cannot confirm, so a party that knows the
    # relationship gets a refusal rather than a 404. Until #85 it copied the
    # parent side's `active` into both projected rows and let the parent in.
    _link_sides_disagree(world)
    facts = authorization._parent_link_facts(PARENT, STUDENT)
    assert facts is not None
    assert facts.forward is not None
    assert facts.forward["status"] == authorization.UNCONFIRMED_LINK_STATUS
    assert facts.matches(PARENT, STUDENT) is False


def test_a_confirmed_link_is_still_projected_as_active(world: AgreementWorld) -> None:
    _link(world)
    facts = authorization._parent_link_facts(PARENT, STUDENT)
    assert facts is not None and facts.matches(PARENT, STUDENT) is True


class ProfileStoreDown(RuntimeError):
    pass


@pytest.mark.parametrize(
    "arrange",
    [
        pytest.param(_binding_revoked, id="binding revoked"),
        pytest.param(_coordinates_disagree, id="binding rows disagree"),
        pytest.param(_binding_parent_suspended, id="parent suspended"),
    ],
)
def test_a_refused_binding_never_reads_the_student_profile(
    world: AgreementWorld,
    monkeypatch: pytest.MonkeyPatch,
    arrange: Callable[[AgreementWorld], None],
) -> None:
    # Refused on its rows or on its parent, a pair must stay refused even when
    # the student's profile cannot be read: the old judge stopped before that
    # read, and one that reads it first turns `None` into an error (#85).
    arrange(world)
    profiles = world.profiles

    def get_user(user_id: str, **_kwargs: object) -> dict | None:
        if user_id == STUDENT:
            raise ProfileStoreDown("student profile unavailable")
        return deepcopy(profiles.get(user_id))

    monkeypatch.setattr(user_repo, "get_user", get_user)
    assert parent_link_service.current_relationship(PARENT, STUDENT) is None


def test_a_valid_binding_still_needs_the_student_profile(
    world: AgreementWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other side of the test above: a pair that would be allowed does
    # reach the student's profile, so a failure there is not silently a "no".
    _bind(world)
    profiles = world.profiles

    def get_user(user_id: str, **_kwargs: object) -> dict | None:
        if user_id == STUDENT:
            raise ProfileStoreDown("student profile unavailable")
        return deepcopy(profiles.get(user_id))

    monkeypatch.setattr(user_repo, "get_user", get_user)
    with pytest.raises(ProfileStoreDown):
        parent_link_service.current_relationship(PARENT, STUDENT)
