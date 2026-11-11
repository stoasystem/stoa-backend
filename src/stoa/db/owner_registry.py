"""Where an account's rows live: its own partitions, and the ones it registered (#397).

Account deletion used to find a user's rows by scanning the whole table, because
most of them sit in partitions keyed by something else - a conversation, a
report, an upload - and say whose they are only in an attribute. This module is
the other half of that answer:

- **Derived partitions.** A fixed list of partition keys that are the user id
  behind a prefix (`USER#{id}`, `ATTEMPTS#{id}`, ...). Deletion queries each one
  directly; nothing is registered for them.
- **Registry rows.** For every other partition an account writes into through
  `stoa.db.table.fenced`, the same transaction puts one row under the account's
  own partition: `USER#{id}/OWNS#{partition}` for the fence owner,
  `USER#{id}/REFERENCED_IN#{partition}` for each `also=` account the write
  merely names (a teacher on a help request, a student on a parent link). One
  row per partition, not per row, and the Put is unconditional and idempotent,
  so it cannot be forgotten and costs no read.

The role lives in the sort key, not in an attribute: two writes that register
the same partition for the same account in different roles keep both rows
instead of the later Put overwriting the earlier role.

Registry rows name the account only through their partition key and
`registry_account`, never `user_id` / `owner_id`: the deletion's predicates match
rows on those, and a registry row is bookkeeping, not the account's data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ENTITY_TYPE = "owner_registry"
OWNER_PREFIX = "OWNS#"
REFERENCE_PREFIX = "REFERENCED_IN#"
ROLE_OWNER = "owner"
ROLE_REFERENCE = "reference"
_ROLE_PREFIX = {ROLE_OWNER: OWNER_PREFIX, ROLE_REFERENCE: REFERENCE_PREFIX}

# Partitions whose key is exactly `prefix + user_id`. Each was checked against
# the repository that builds it (#397). A prefix whose key carries more than the
# id - `NOTIFICATION_PUSH_TOKEN#{user}#{token_reference}` - is not here: it
# cannot be queried from the id alone, so it is registered like any other.
DERIVED_PREFIXES: tuple[str, ...] = (
    "USER#",  # profile, fence, identity inventory, sign-ins, deletion bookkeeping
    "ATTEMPTS#",  # practice_repo
    "REVIEW#",  # review_repo / practice_repo
    "ACTIVITY#",  # practice_repo.activity_partition
    "PROGRESS#",  # practice_repo
    "QUIZ#",  # practice_repo
    "USAGE#",  # usage_period / practice_repo
    "USAGE_LEDGER#",  # usage_ledger_repo
    "STORAGE#",  # attachment_repo storage usage
    "OWNER#",  # attachment_repo owner index rows
    "ALLOWANCE#",  # allowance_repo, keyed by beneficiary
    "LEARNING_MEMORY#",  # adaptive_learning_repo
    "CURRICULUM_SIGNAL_OWNER#",  # curriculum_analytics_repo owner manifest
    "STUDENT#",  # parent_link_repo (student side of a link)
    "PARENT#",  # parent_link_repo (parent side of a link)
    "NOTIFICATION_PREF#",  # notification_repo.preference_pk
    "NOTIFICATION_DELIVERY#",  # notification_repo.delivery_intent_pk
    "TEACHER_ASSIGNMENT#",  # question_repo, keyed by teacher
    "PASSWORD_CHANGE_CODE#",  # password_change_code_service
    "PASSWORD_CHANGE_QUOTA#",  # password_change_code_service
    "PARENT_LINK_REQUEST_QUOTA#",  # routers/parents, keyed by requester
    # Billing, keyed by the paying parent (excluded from deletion, but still the
    # parent's own partitions: nothing to register).
    "BILLING#",
    "CHECKOUT_OPEN#",
    "SUBSCRIPTION_BILLING#",
    "SUBSCRIPTION_OPEN#",
    "PAID_GRANT#",
    "PAID_GRANT_HISTORY#",
    "PAID_TRANSITION#",
    "PLAN_GRANT#",
    "ALLOWANCE_PLAN#",
)


def derived_partitions(user_id: str) -> tuple[str, ...]:
    """Every partition key the user id alone determines, in a fixed order."""
    return tuple(f"{prefix}{_account(user_id)}" for prefix in DERIVED_PREFIXES)


def is_derived_for(pk: object, user_id: str) -> bool:
    """Whether `pk` is one of `user_id`'s derived partitions."""
    return isinstance(pk, str) and pk in derived_partitions(user_id)


def registry_key(user_id: str, partition: str, role: str = ROLE_OWNER) -> dict[str, str]:
    prefix = _ROLE_PREFIX.get(role)
    if prefix is None:
        raise ValueError(f"unknown registry role: {role}")
    if not isinstance(partition, str) or not partition:
        raise ValueError("a registry row names a partition")
    return {"PK": f"USER#{_account(user_id)}", "SK": f"{prefix}{partition}"}


def registry_item(user_id: str, partition: str, role: str = ROLE_OWNER) -> dict[str, Any]:
    return {
        **registry_key(user_id, partition, role),
        "entity_type": ENTITY_TYPE,
        "registry_account": _account(user_id),
        "registered_pk": partition,
        "role": role,
    }


def is_registry_row(item: Mapping[str, Any]) -> bool:
    return item.get("entity_type") == ENTITY_TYPE or str(item.get("SK") or "").startswith(
        (OWNER_PREFIX, REFERENCE_PREFIX)
    )


def written_partitions(operations: Iterable[Mapping[str, Any]]) -> list[str]:
    """The partitions `operations` create or change, in first-seen order.

    Puts and Updates only: a Delete removes, and a ConditionCheck reads.
    """
    found: list[str] = []
    for operation in operations:
        if not isinstance(operation, Mapping) or len(operation) != 1:
            continue
        ((action, body),) = operation.items()
        if not isinstance(body, Mapping):
            continue
        if action == "Put":
            key = body.get("Item")
        elif action == "Update":
            key = body.get("Key")
        else:
            continue
        pk = key.get("PK") if isinstance(key, Mapping) else None
        if isinstance(pk, str) and pk and pk not in found:
            found.append(pk)
    return found


def registry_operations(
    owner: str,
    references: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The registry Puts a fenced write of `operations` carries.

    One per (account, role, partition): the owner for every partition written
    that is not one of its own derived partitions, each `also=` account the
    same as a reference. A key the operations themselves already touch is left
    out, so a transaction never names one item twice.
    """
    partitions = written_partitions(operations)
    taken = {_operation_key(operation) for operation in operations}
    wanted: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for account, role in ((owner, ROLE_OWNER), *((other, ROLE_REFERENCE) for other in references)):
        own = set(derived_partitions(account))
        for partition in partitions:
            if partition in own:
                continue
            item = registry_item(account, partition, role)
            key = (item["PK"], item["SK"])
            if key in seen or key in taken:
                continue
            seen.add(key)
            wanted.append({"Put": {"Item": item}})
    return wanted


def _operation_key(operation: Mapping[str, Any]) -> tuple[str, str] | None:
    if not isinstance(operation, Mapping) or len(operation) != 1:
        return None
    ((_, body),) = operation.items()
    if not isinstance(body, Mapping):
        return None
    key = body.get("Key") or body.get("Item")
    if not isinstance(key, Mapping):
        return None
    return (str(key.get("PK", "")), str(key.get("SK", "")))


def _account(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("an account id is required")
    return user_id.strip()
