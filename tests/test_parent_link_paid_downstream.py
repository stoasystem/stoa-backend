"""Card 003: the many-to-many parent links reach billing, entitlement and allowance.

The gate these tests defend is not the read-side judgement but the condition
writes: a link that is revoked between the pre-read and the commit has to cancel
the transaction, exactly as a revoked profile binding always did.
"""

# These read `_resolve_paid_scope`, not `_resolve_scope`. What each one holds is
# that a relationship which is not a live paid one yields no *paid* allowance.
# `_resolve_scope` also answers the figure a student has by being assigned one,
# which every student now has, so asking it here would be asking a different
# question and would never be None again.


from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

import pytest

from dynamodb_expression_assertions import assert_expression_placeholders_closed
from stoa.config import Settings
from stoa.db.repositories import (
    account_deletion_repo,
    billing_fact_repo,
    parent_link_repo,
    user_repo,
)
from stoa.models.billing import BillingPlanId
from stoa.services import (
    entitlement_service,
    paid_entitlement_service,
    parent_link_service,
    teacher_support_allowance_service,
)


PARENT = "parent-1"
STUDENT = "student-1"
DIGEST = "a" * 64
NOW_TEXT = "2026-03-25T12:00:00+00:00"
NOW = datetime(2026, 3, 25, 12, tzinfo=timezone.utc)

_TERM = re.compile(r"^\s*(\S+)\s*=\s*(\S+)\s*$")
_EXISTS = re.compile(r"^\s*attribute_(not_)?exists\(([^)]+)\)\s*$")


class ConditionalTable:
    """In-memory single table that really evaluates the conditions it is given.

    A double that skips `ConditionCheck` would let every fence in this card pass
    by construction, which is the failure mode these tests exist to catch, so an
    expression this evaluator does not understand is an error, never a pass.
    """

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.transactions: list[list[dict[str, Any]]] = []

    def put(self, item: dict[str, Any]) -> None:
        self.items[(item["PK"], item["SK"])] = deepcopy(item)

    def get_item(self, *, Key, ConsistentRead: bool = False, **_kwargs):  # noqa: N803
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(self, *, Item, **_kwargs):  # noqa: N803
        self.put(Item)

    def query(self, **kwargs):
        partition, prefix = _key_condition(kwargs["KeyConditionExpression"])
        return {
            "Items": [
                deepcopy(item)
                for (pk, sk), item in self.items.items()
                if pk == partition and sk.startswith(prefix)
            ]
        }

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        staged = deepcopy(self.items)
        for operation in operations:
            if "ConditionCheck" in operation:
                check = operation["ConditionCheck"]
                key = (check["Key"]["PK"], check["Key"]["SK"])
                if not _evaluate(staged.get(key), check):
                    raise account_deletion_repo.AccountDeletionConflict(
                        f"condition check refused for {key}"
                    )
                continue
            put = operation["Put"]
            item = deepcopy(put["Item"])
            key = (item["PK"], item["SK"])
            if not _evaluate(staged.get(key), put):
                raise account_deletion_repo.AccountDeletionConflict(
                    f"conditional put refused for {key}"
                )
            staged[key] = item
        self.items = staged
        self.transactions.append(deepcopy(operations))


def _key_condition(expression: Any) -> tuple[str, str]:
    terms: dict[tuple[str, str], str] = {}
    pending = [expression]
    while pending:
        built = pending.pop().get_expression()
        if built["operator"] == "AND":
            pending.extend(built["values"])
            continue
        terms[(built["values"][0].name, built["operator"])] = built["values"][1]
    return terms[("PK", "=")], terms[("SK", "begins_with")]


def _evaluate(item: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    expression = payload.get("ConditionExpression")
    if not expression:
        return True
    names = payload.get("ExpressionAttributeNames", {})
    values = payload.get("ExpressionAttributeValues", {})
    for term in str(expression).split(" AND "):
        exists = _EXISTS.match(term)
        if exists is not None:
            present = item is not None and names.get(
                exists.group(2), exists.group(2)
            ) in item
            if bool(exists.group(1)) is present:
                return False
            continue
        equality = _TERM.match(term)
        if equality is None:
            raise AssertionError(f"unsupported condition term: {term!r}")
        left, right = equality.groups()
        if item is None:
            return False
        stored = item.get(names.get(left, left))
        if stored != values[right]:
            return False
    return True


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=2,
        free_tier_daily_chat_message_limit=8,
        free_tier_daily_hint_limit=2,
        standard_tier_daily_question_limit=30,
        standard_tier_daily_chat_message_limit=80,
        standard_tier_daily_hint_limit=30,
        premium_tier_daily_question_limit=100,
        premium_tier_daily_chat_message_limit=200,
        premium_tier_daily_hint_limit=80,
    )


def _grant_item(
    *,
    source: str,
    plan_id: BillingPlanId = BillingPlanId.TEACHER_SUPPORTED,
    parent_id: str = PARENT,
) -> dict[str, Any]:
    grant: dict[str, Any] = {
        "PK": f"PAID_GRANT#{parent_id}",
        "SK": f"BENEFICIARY#{STUDENT}",
        "entity_type": "beneficiary_grant",
        "schema_version": paid_entitlement_service.GRANT_SCHEMA_VERSION,
        "parent_id": parent_id,
        "beneficiary_id": STUDENT,
        "grant_status": "active",
        "command_id": "cmd-1",
        "subscription_id_digest": DIGEST,
        "grant_version": 13,
        "plan_id": str(plan_id),
        "plan_version": 7,
        "allowance_version": 11,
        "activation_version": 13,
        "activated_at": NOW_TEXT,
        "relationship_source": source,
        "parent_profile_version": 11,
        "parent_account_fence_generation": 4,
        "student_profile_version": 21,
        "student_account_fence_generation": 6,
    }
    if source == paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING:
        grant["forward_relationship_version"] = 8
        grant["reverse_relationship_version"] = 8
    return grant


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> ConditionalTable:
    fake = ConditionalTable()
    for module in (
        parent_link_repo,
        user_repo,
        account_deletion_repo,
        entitlement_service,
        paid_entitlement_service,
        teacher_support_allowance_service,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    fake.put(
        {
            "PK": f"USER#{PARENT}",
            "SK": "PROFILE",
            "user_id": PARENT,
            "role": "parent",
            "account_status": "active",
            "version": 11,
            "subscription_tier": "free_trial",
            "date_of_birth": "2000-01-01",
        }
    )
    fake.put(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "PROFILE",
            "user_id": STUDENT,
            "role": "student",
            "account_status": "active",
            "version": 21,
            "subscription_tier": "free_trial",
            "date_of_birth": "2000-01-01",
        }
    )
    for user_id, generation in ((PARENT, 4), (STUDENT, 6)):
        fake.put(
            {
                "PK": f"USER#{user_id}",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": generation,
            }
        )
    return fake


def _bind_legacy(fake: ConditionalTable) -> None:
    """Reproduce the pre-002 shape: profile fields plus two versioned binding rows."""
    profile = fake.items[(f"USER#{STUDENT}", "PROFILE")]
    fake.put({**profile, "parent_id": PARENT, "parent_binding_status": "active"})
    for key in ((f"USER#{PARENT}", f"CHILD#{STUDENT}"), (f"USER#{STUDENT}", f"PARENT#{PARENT}")):
        fake.put(
            {
                "PK": key[0],
                "SK": key[1],
                "parent_id": PARENT,
                "student_id": STUDENT,
                "relationship": "child",
                "status": "active",
                "version": 8,
            }
        )


def _link_active(fake: ConditionalTable) -> None:
    parent_link_service.assign_link(
        parent_id=PARENT, student_id=STUDENT, actor_id="admin-1", now=NOW_TEXT
    )
    assert (f"PARENT#{PARENT}", f"CHILD#{STUDENT}") in fake.items


def _revoke_link() -> None:
    parent_link_repo.transition_link(
        parent_id=PARENT,
        student_id=STUDENT,
        expected_status=parent_link_repo.STATUS_ACTIVE,
        next_status=parent_link_repo.STATUS_REJECTED,
        updated_by="admin-1",
        link_updated_at=NOW_TEXT,
    )


def _activation_request() -> billing_fact_repo.PaidActivationRequest:
    return billing_fact_repo.PaidActivationRequest(
        command_id="cmd-1",
        parent_id=PARENT,
        expected_command_version=4,
        provider_customer_id_digest="b" * 64,
        provider_subscription_id_digest=DIGEST,
        price_id="price_test_student",
        environment="test",
        plan_id=BillingPlanId.STUDENT,
        plan_version=2,
        allowance_version=2,
        activation_version=7,
        paid_invoice_fact_id="fact-invoice",
        active_subscription_fact_id="fact-subscription",
        activated_at=NOW_TEXT,
    )


def _command() -> dict[str, Any]:
    return {
        "command_id": "cmd-1",
        "parent_id": PARENT,
        "beneficiary_ids": [STUDENT],
        "provider_subscription_id_digest": DIGEST,
        "plan_id": BillingPlanId.STUDENT.value,
        "plan_version": 2,
    }


def _build(table: ConditionalTable):
    return paid_entitlement_service.build_paid_activation_operations(
        _activation_request(), command=_command(), table=table
    )


# --- 1. a link-only family reaches the paid pool ---------------------------


def test_link_only_family_is_provable_for_a_paid_grant(table: ConditionalTable) -> None:
    _link_active(table)

    built = _build(table)

    grant = built.grant_items[0]
    assert grant["beneficiary_id"] == STUDENT
    assert (
        grant["relationship_source"] == paid_entitlement_service.RELATIONSHIP_SOURCE_LINK
    )
    assert "forward_relationship_version" not in grant
    targets = [
        (op["ConditionCheck"]["Key"]["PK"], op["ConditionCheck"]["Key"]["SK"])
        for op in built.grant_operations
    ]
    assert (f"PARENT#{PARENT}", f"CHILD#{STUDENT}") in targets
    assert (f"STUDENT#{STUDENT}", f"PARENT#{PARENT}") in targets
    # The link relationship is not mirrored onto the profile, so the profile
    # condition must not claim it.
    student_profile_check = next(
        op["ConditionCheck"]
        for op in built.grant_operations
        if op["ConditionCheck"]["Key"] == {"PK": f"USER#{STUDENT}", "SK": "PROFILE"}
    )
    assert ":parent_id" not in student_profile_check["ExpressionAttributeValues"]
    for operation in built.grant_operations:
        assert_expression_placeholders_closed(operation)
    account_deletion_repo.transact(list(built.grant_operations), table=table)


def test_link_only_student_enters_the_paid_entitlement_pool(
    table: ConditionalTable,
) -> None:
    _link_active(table)
    table.put(_grant_item(source=paid_entitlement_service.RELATIONSHIP_SOURCE_LINK))

    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert resolved["parentId"] == PARENT
    assert resolved["source"] == "paid_beneficiary_grant"
    assert resolved["effectivePlan"] == "teacher_supported"
    assert resolved["bindingStatus"] == "active"


def test_parent_child_entitlement_list_unions_bindings_and_links(
    table: ConditionalTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _link_active(table)
    table.put(
        {
            "PK": "USER#student-legacy",
            "SK": "PROFILE",
            "user_id": "student-legacy",
            "role": "student",
            "account_status": "active",
            "version": 31,
            "subscription_tier": "free_trial",
            "date_of_birth": "2000-01-01",
        }
    )
    monkeypatch.setattr(
        entitlement_service.user_repo,
        "list_parent_student_bindings",
        lambda _parent_id: [
            {"student_id": "student-legacy", "status": "active"},
            {"student_id": "student-dropped", "status": "revoked"},
        ],
    )

    listed = entitlement_service.list_parent_child_entitlements(
        PARENT, settings=_settings()
    )

    assert [item["studentId"] for item in listed] == ["student-legacy", STUDENT]


def test_link_only_student_occupies_the_teacher_support_allowance(
    table: ConditionalTable,
) -> None:
    _link_active(table)
    table.put(_grant_item(source=paid_entitlement_service.RELATIONSHIP_SOURCE_LINK))

    result = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id="question-1",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=lambda operations: _persist(table, operations),
        table=table,
    )

    assert result.disposition.value == "admitted"
    assert result.admission is not None
    assert result.admission.post_admission_count == 1


def _persist(table: ConditionalTable, operations: tuple[dict[str, Any], ...]) -> bool:
    try:
        account_deletion_repo.transact(list(operations), table=table)
    except account_deletion_repo.AccountDeletionConflict:
        return False
    return True


# --- 2. the atomic fence: revoked between the pre-read and the commit -------


def test_link_revoked_after_the_preread_cancels_the_paid_transaction(
    table: ConditionalTable,
) -> None:
    _link_active(table)
    built = _build(table)

    _revoke_link()

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.transact(list(built.grant_operations), table=table)


def test_link_revoked_after_the_preread_cancels_the_support_admission(
    table: ConditionalTable,
) -> None:
    _link_active(table)
    table.put(_grant_item(source=paid_entitlement_service.RELATIONSHIP_SOURCE_LINK))

    revoked: list[bool] = []

    def persist(operations: tuple[dict[str, Any], ...]) -> bool:
        if not revoked:
            revoked.append(True)
            _revoke_link()
        return _persist(table, operations)

    result = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id="question-2",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=persist,
        table=table,
    )

    assert result.disposition.value == "retryable"
    assert not [
        item
        for item in table.items.values()
        if item.get("entity_type") == "teacher_support_counter"
    ]


# --- 3. negative control: the legacy binding is untouched ------------------


def test_legacy_binding_keeps_its_versioned_conditions(table: ConditionalTable) -> None:
    _bind_legacy(table)

    built = _build(table)

    grant = built.grant_items[0]
    assert (
        grant["relationship_source"]
        == paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING
    )
    assert grant["forward_relationship_version"] == 8
    assert grant["reverse_relationship_version"] == 8
    targets = [
        (op["ConditionCheck"]["Key"]["PK"], op["ConditionCheck"]["Key"]["SK"])
        for op in built.grant_operations
    ]
    assert (f"USER#{PARENT}", f"CHILD#{STUDENT}") in targets
    assert (f"USER#{STUDENT}", f"PARENT#{PARENT}") in targets
    assert (f"PARENT#{PARENT}", f"CHILD#{STUDENT}") not in targets
    student_profile_check = next(
        op["ConditionCheck"]
        for op in built.grant_operations
        if op["ConditionCheck"]["Key"] == {"PK": f"USER#{STUDENT}", "SK": "PROFILE"}
    )
    assert student_profile_check["ExpressionAttributeValues"][":parent_id"] == PARENT
    for operation in built.grant_operations:
        assert_expression_placeholders_closed(operation)
    account_deletion_repo.transact(list(built.grant_operations), table=table)


def test_grant_stored_before_this_card_keeps_the_legacy_conditions(
    table: ConditionalTable,
) -> None:
    """Grants written before card 003 carry no `relationship_source` at all."""
    _bind_legacy(table)
    legacy_grant = _grant_item(
        source=paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING
    )
    del legacy_grant["relationship_source"]
    table.put(legacy_grant)
    captured: list[tuple[dict[str, Any], ...]] = []

    result = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id="question-legacy",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=lambda operations: (
            captured.append(operations) or _persist(table, operations)
        ),
        table=table,
    )

    assert result.disposition.value == "admitted"
    targets = [
        (op["ConditionCheck"]["Key"]["PK"], op["ConditionCheck"]["Key"]["SK"])
        for op in captured[0]
        if "ConditionCheck" in op
    ]
    assert (f"USER#{PARENT}", f"CHILD#{STUDENT}") in targets
    assert (f"PARENT#{PARENT}", f"CHILD#{STUDENT}") not in targets


def test_legacy_binding_version_bump_still_cancels_the_transaction(
    table: ConditionalTable,
) -> None:
    _bind_legacy(table)
    built = _build(table)

    forward = table.items[(f"USER#{PARENT}", f"CHILD#{STUDENT}")]
    table.put({**forward, "version": 9})

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.transact(list(built.grant_operations), table=table)


# --- 4. and 5. pending and half links do not count -------------------------


def test_pending_link_is_not_a_paid_relationship(table: ConditionalTable) -> None:
    parent_link_service.request_link(
        requester_id=PARENT, counterpart_id=STUDENT, now=NOW_TEXT
    )

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        _build(table)
    assert (
        teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table) is None
    )
    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )
    assert resolved["parentId"] is None
    assert resolved["blockingReason"] == "missing_parent_binding"


@pytest.mark.parametrize("dropped", ["parent", "student"])
def test_half_stored_link_is_not_a_paid_relationship(
    table: ConditionalTable, dropped: str
) -> None:
    _link_active(table)
    key = (
        (f"PARENT#{PARENT}", f"CHILD#{STUDENT}")
        if dropped == "parent"
        else (f"STUDENT#{STUDENT}", f"PARENT#{PARENT}")
    )
    del table.items[key]

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        _build(table)
    assert (
        teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table) is None
    )


def test_rejected_link_is_not_a_paid_relationship(table: ConditionalTable) -> None:
    _link_active(table)
    _revoke_link()

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        _build(table)


# --- 6. card 003 audit follow-up -------------------------------------------

BINDING = paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING
LINK = paid_entitlement_service.RELATIONSHIP_SOURCE_LINK
OTHER_PARENT = "parent-zzz"
FIRST_PARENT = "parent-aaa"


def _put_parent(fake: ConditionalTable, parent_id: str, *, generation: int = 4) -> None:
    fake.put(
        {
            "PK": f"USER#{parent_id}",
            "SK": "PROFILE",
            "user_id": parent_id,
            "role": "parent",
            "account_status": "active",
            "version": 11,
            "subscription_tier": "free_trial",
            "date_of_birth": "2000-01-01",
        }
    )
    fake.put(
        {
            "PK": f"USER#{parent_id}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": generation,
        }
    )


def _link_active_for(
    fake: ConditionalTable, parent_id: str, *, relationship: str = "child"
) -> None:
    parent_link_service.assign_link(
        parent_id=parent_id,
        student_id=STUDENT,
        actor_id="admin-1",
        relationship=relationship,
        now=NOW_TEXT,
    )
    assert (f"PARENT#{parent_id}", f"CHILD#{STUDENT}") in fake.items


def _student_profile(fake: ConditionalTable) -> dict[str, Any]:
    return fake.items[(f"USER#{STUDENT}", "PROFILE")]


def _revoke_legacy_binding(fake: ConditionalTable) -> None:
    """The exact shape admin leaves behind: profile revoked, both rows revoked, version bumped."""
    profile = _student_profile(fake)
    fake.put({**profile, "parent_id": PARENT, "parent_binding_status": "revoked"})
    for key in (
        (f"USER#{PARENT}", f"CHILD#{STUDENT}"),
        (f"USER#{STUDENT}", f"PARENT#{PARENT}"),
    ):
        row = fake.items[key]
        fake.put({**row, "status": "revoked", "version": 9})


def _admit(fake: ConditionalTable, case_id: str) -> Any:
    return teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=lambda operations: _persist(fake, operations),
        table=fake,
    )


# --- A1: one parent must never receive the other parent's user id ----------


def test_a_shared_child_never_hands_one_parent_the_other_parents_identity(
    table: ConditionalTable,
) -> None:
    """Audit A1: `parentId` reached the parent-facing billing responses verbatim."""
    _put_parent(table, FIRST_PARENT)
    _put_parent(table, OTHER_PARENT)
    _link_active_for(table, FIRST_PARENT)
    _link_active_for(table, OTHER_PARENT)
    table.put(_grant_item(source=LINK, parent_id=OTHER_PARENT))

    listed = entitlement_service.list_parent_child_entitlements(
        FIRST_PARENT, settings=_settings()
    )

    assert [item["studentId"] for item in listed] == [STUDENT]
    assert all(item["parentId"] in (None, FIRST_PARENT) for item in listed)
    assert OTHER_PARENT not in repr(listed)
    # The child's own plan is still the truth and still reported.
    assert listed[0]["effectivePlan"] == "teacher_supported"


def test_the_paying_parents_own_list_still_names_the_paying_parent(
    table: ConditionalTable,
) -> None:
    """The scrub is for the other parent only; the payer's own row is untouched."""
    _put_parent(table, OTHER_PARENT)
    _link_active_for(table, OTHER_PARENT)
    table.put(_grant_item(source=LINK, parent_id=OTHER_PARENT))

    listed = entitlement_service.list_parent_child_entitlements(
        OTHER_PARENT, settings=_settings()
    )

    assert [item["parentId"] for item in listed] == [OTHER_PARENT]


# --- A2: a stale `relationship_source` must not strand a live family -------


def test_a_stale_binding_source_admits_through_the_live_link(
    table: ConditionalTable,
) -> None:
    """Audit A2: grant says `profile_binding`, the binding is gone, the link is live."""
    _bind_legacy(table)
    _link_active(table)
    table.put(_grant_item(source=BINDING))
    _revoke_legacy_binding(table)

    result = _admit(table, "question-stale-binding")

    assert result.disposition.value == "admitted"


def test_a_stale_link_source_admits_through_the_live_binding(
    table: ConditionalTable,
) -> None:
    """The mirror image: grant says `parent_student_link`, only the binding survives."""
    _link_active(table)
    table.put(_grant_item(source=LINK))
    _revoke_link()
    _bind_legacy(table)
    forward = table.items[(f"USER#{PARENT}", f"CHILD#{STUDENT}")]
    table.put({**forward, "version": 12})
    reverse = table.items[(f"USER#{STUDENT}", f"PARENT#{PARENT}")]
    table.put({**reverse, "version": 12})
    captured: list[tuple[dict[str, Any], ...]] = []

    result = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id="question-stale-link",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=lambda operations: (
            captured.append(operations) or _persist(table, operations)
        ),
        table=table,
    )

    assert result.disposition.value == "admitted"
    versions = [
        op["ConditionCheck"]["ExpressionAttributeValues"].get(":version")
        for op in captured[0]
        if "ConditionCheck" in op
        and op["ConditionCheck"]["Key"]["SK"].startswith(("CHILD#", "PARENT#"))
    ]
    # The live row versions, not the ones the link-sourced grant never stored.
    assert versions == [12, 12]


def test_a_relationship_that_died_on_both_tables_is_denied_not_retried(
    table: ConditionalTable,
) -> None:
    """A dead relationship is a clean terminal denial, never a permanent 503.

    The denial is of the *paid* allowance. A student whose parent relationship
    died still has the figure they were assigned, and spending that is the right
    answer - what must not happen is the dead relationship being retried until
    the caller gives up, which is a 503 for a student who did nothing wrong.
    """
    _bind_legacy(table)
    table.put(_grant_item(source=BINDING))
    _revoke_legacy_binding(table)

    assert (
        teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table)
        is None
    )

    result = _admit(table, "question-dead")

    # Terminal either way: admitted on the student's own figure, never retryable.
    assert result.disposition.value != "retryable"
    assert result.disposition.value == "admitted"
    assert result.admission is not None
    assert result.admission.limit == (
        teacher_support_allowance_service.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES
    )
    # And it is the student's own scope: the assigned one, not the dead grant's.
    assert result.admission.support_scope_id == (
        teacher_support_allowance_service._resolve_assigned_scope(
            STUDENT, table=table
        ).support_scope_id
    )


# --- B1: one judge, one answer per cell ------------------------------------

# profile claim x binding rows x link -> one verdict, read the same way by all
# three services. `authority` is the shared judge; `scope` is whether the paid
# relationship is alive for teacher support and entitlement alike; `write` is
# what minting a *new* grant does, which additionally needs the two binding
# rows to be readable and bidirectional.
_RELATIONSHIP_CELLS = (
    ("binding claimed, rows active, no link", "active", "active", None, BINDING, BINDING, BINDING),
    ("binding claimed, rows active, link active", "active", "active", "active", BINDING, BINDING, BINDING),
    ("binding claimed, rows missing, link active", "active", None, "active", BINDING, None, "refused"),
    ("binding claimed, rows not bidirectional", "active", "contradicting", "active", BINDING, None, "refused"),
    ("binding revoked, rows revoked, link active", "revoked", "revoked", "active", LINK, LINK, LINK),
    ("binding revoked, rows revoked, no link", "revoked", "revoked", None, None, None, "refused"),
    ("binding status absent, rows active, link active", "absent", "active", "active", LINK, LINK, LINK),
    ("binding status absent, rows active, no link", "absent", "active", None, None, None, "refused"),
    ("no claim, link active", None, None, "active", LINK, LINK, LINK),
    ("no claim, link pending", None, None, "pending", None, None, "refused"),
    ("no claim, link is not a child link", None, None, "neighbour", None, None, "refused"),
    ("no claim, no link", None, None, None, None, None, "refused"),
)


def _apply_cell(
    fake: ConditionalTable,
    *,
    claim: str | None,
    rows: str | None,
    link: str | None,
) -> None:
    profile = _student_profile(fake)
    if claim == "active":
        fake.put({**profile, "parent_id": PARENT, "parent_binding_status": "active"})
    elif claim == "revoked":
        fake.put({**profile, "parent_id": PARENT, "parent_binding_status": "revoked"})
    elif claim == "absent":
        fake.put({**profile, "parent_id": PARENT})
    if rows is not None:
        for key in (
            (f"USER#{PARENT}", f"CHILD#{STUDENT}"),
            (f"USER#{STUDENT}", f"PARENT#{PARENT}"),
        ):
            fake.put(
                {
                    "PK": key[0],
                    "SK": key[1],
                    "parent_id": PARENT,
                    "student_id": STUDENT,
                    "relationship": "neighbour" if rows == "contradicting" else "child",
                    "status": "revoked" if rows == "revoked" else "active",
                    "version": 8,
                }
            )
    if link == "active":
        _link_active(fake)
    elif link == "pending":
        parent_link_service.request_link(
            requester_id=PARENT, counterpart_id=STUDENT, now=NOW_TEXT
        )
    elif link == "neighbour":
        _link_active_for(fake, PARENT, relationship="neighbour")


@pytest.mark.parametrize(
    ("name", "claim", "rows", "link", "authority_source", "scope_source", "write"),
    _RELATIONSHIP_CELLS,
    ids=[cell[0] for cell in _RELATIONSHIP_CELLS],
)
def test_every_service_reads_the_same_relationship_cell(
    table: ConditionalTable,
    name: str,
    claim: str | None,
    rows: str | None,
    link: str | None,
    authority_source: str | None,
    scope_source: str | None,
    write: str,
) -> None:
    """Audit B1: three services used three different predicates for one fact."""
    _apply_cell(table, claim=claim, rows=rows, link=link)
    table.put(_grant_item(source=authority_source or BINDING))
    profile = _student_profile(table)

    authority = paid_entitlement_service.relationship_authority(
        PARENT, STUDENT, student=profile
    )
    scope = teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table)
    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert (authority.source if authority is not None else None) == authority_source, name
    assert (scope.relationship_source if scope is not None else None) == scope_source, name
    assert resolved["parentId"] == (PARENT if authority_source else None), name
    # The two consumer services never disagree about whether the paid
    # relationship is alive, nor about which parent runs it.
    paid_alive = scope is not None
    assert (resolved["source"] == "paid_beneficiary_grant") is paid_alive, name
    assert (resolved["effectivePlan"] == "teacher_supported") is paid_alive, name
    if paid_alive:
        assert scope.parent_id == resolved["parentId"], name

    if write == "refused":
        with pytest.raises(paid_entitlement_service.PaidGrantConflict):
            _build(table)
    else:
        assert _build(table).grant_items[0]["relationship_source"] == write, name


def test_a_contradicting_binding_never_falls_through_to_the_link(
    table: ConditionalTable,
) -> None:
    """A half-broken legacy binding is a refusal; softening it would mint a link grant."""
    _apply_cell(table, claim="active", rows="contradicting", link="active")

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        _build(table)


# --- B2: which parent is picked, and which one is charged ------------------


def test_the_grant_holder_wins_over_the_alphabetically_first_link_parent(
    table: ConditionalTable,
) -> None:
    """Pinned as-is: this rule is the one that decides whose allowance is spent.

    Card 007 froze every route that could mint a new beneficiary grant, so the
    rows this exercises are legacy data from now on. The rule itself was not
    touched and still has to answer for them, which is why the assertion is
    unchanged rather than rewritten to a frozen state it does not have.
    """
    _put_parent(table, FIRST_PARENT)
    _put_parent(table, OTHER_PARENT)
    _link_active_for(table, FIRST_PARENT)
    _link_active_for(table, OTHER_PARENT)
    table.put(_grant_item(source=LINK, parent_id=OTHER_PARENT))

    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert resolved["parentId"] == OTHER_PARENT
    assert resolved["source"] == "paid_beneficiary_grant"


def test_without_any_grant_the_first_link_parent_is_chosen_deterministically(
    table: ConditionalTable,
) -> None:
    _put_parent(table, FIRST_PARENT)
    _put_parent(table, OTHER_PARENT)
    _link_active_for(table, OTHER_PARENT)
    _link_active_for(table, FIRST_PARENT)

    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert resolved["parentId"] == FIRST_PARENT


# --- B3: manual_override travels down a link -------------------------------


def test_manual_override_reaches_a_link_only_child_without_a_grant(
    table: ConditionalTable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The product decision this used to flag was taken: card 007 froze it.

    The override bypassed the grant fence and the 1-3 beneficiary cap, so it
    handed out paid access with no billing fact and no cap behind it. Pinned as
    the frozen state rather than deleted -- `manual_override` rows already
    exist in the table, so this path stays reachable from data even with every
    paid route refusing -- and the second half records what unfreezing restores.
    """
    _link_active(table)
    table.put(
        {
            "PK": f"SUBSCRIPTION_BILLING#{PARENT}",
            "SK": "SUMMARY",
            "billing_status": "manual_override",
            "subscription_tier": "family",
        }
    )

    frozen = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert frozen["effectivePlan"] == "free_trial"
    assert frozen["source"] == "free_tier"
    assert frozen["blockingReason"] == "billing_frozen"

    monkeypatch.setattr(entitlement_service, "MANUAL_BILLING_OVERRIDE_ENABLED", True)
    unfrozen = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )

    assert unfrozen["effectivePlan"] == "family"
    assert unfrozen["source"] == "manual_override"


# --- B4: a link is only a paid relationship when it is a child link --------


def test_a_non_child_link_is_not_a_paid_relationship(table: ConditionalTable) -> None:
    """`relationship` is caller-supplied text; the legacy path always fenced it."""
    _link_active_for(table, PARENT, relationship="neighbour")
    table.put(_grant_item(source=LINK))

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        _build(table)
    assert (
        teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table) is None
    )
    resolved = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=_settings()
    )
    assert resolved["parentId"] is None


def test_the_link_conditions_fence_the_relationship_field(
    table: ConditionalTable,
) -> None:
    _link_active(table)
    built = _build(table)

    forward = table.items[(f"PARENT#{PARENT}", f"CHILD#{STUDENT}")]
    table.put({**forward, "relationship": "neighbour"})

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.transact(list(built.grant_operations), table=table)


# --- B5: a profile-bound student never reaches a link parent ---------------


def test_a_profile_bound_student_never_reaches_a_paying_link_parent(
    table: ConditionalTable,
) -> None:
    """Pinned as-is: the legacy binding answers alone, so the link payer is invisible."""
    _bind_legacy(table)
    _put_parent(table, OTHER_PARENT)
    _link_active_for(table, OTHER_PARENT)
    table.put(_grant_item(source=LINK, parent_id=OTHER_PARENT))

    assert [
        parent_id
        for parent_id, _ in paid_entitlement_service.authorizing_parents(
            STUDENT, student=_student_profile(table)
        )
    ] == [PARENT]
    assert (
        teacher_support_allowance_service._resolve_paid_scope(STUDENT, table=table) is None
    )
    assert (
        entitlement_service.resolve_student_entitlement(STUDENT, settings=_settings())[
            "parentId"
        ]
        == PARENT
    )


# --- B6: a link grant carries no binding versions, upgrades included -------


def test_a_link_grant_carries_no_binding_versions_and_a_binding_grant_does(
    table: ConditionalTable,
) -> None:
    _link_active(table)

    link_grant = _build(table).grant_items[0]

    assert "forward_relationship_version" not in link_grant
    assert "reverse_relationship_version" not in link_grant

    table.items.pop((f"PARENT#{PARENT}", f"CHILD#{STUDENT}"))
    table.items.pop((f"STUDENT#{STUDENT}", f"PARENT#{PARENT}"))
    _bind_legacy(table)

    binding_grant = _build(table).grant_items[0]

    assert binding_grant["forward_relationship_version"] == 8
    assert binding_grant["reverse_relationship_version"] == 8


def test_an_upgrade_onto_a_link_relationship_drops_the_binding_versions(
    table: ConditionalTable,
) -> None:
    """The upgrade rewrites a stored grant, so the stale versions must be popped."""
    _link_active(table)
    table.put(_grant_item(source=BINDING, plan_id=BillingPlanId.STUDENT))

    result = paid_entitlement_service.apply_paid_upgrade(
        parent_id=PARENT,
        beneficiary_ids=[STUDENT],
        subscription_id_digest=DIGEST,
        command_id="cmd-upgrade",
        plan_id=BillingPlanId.TEACHER_SUPPORTED,
        plan_version=8,
        allowance_version=12,
        activation_version=14,
        activated_at=NOW,
        table=table,
    )

    assert result.disposition.value == "upgraded"
    upgraded = next(
        op["Put"]["Item"]
        for op in result.operations
        if "Put" in op
        and op["Put"]["Item"].get("entity_type") == "beneficiary_grant"
    )
    assert upgraded["relationship_source"] == LINK
    assert "forward_relationship_version" not in upgraded
    assert "reverse_relationship_version" not in upgraded
