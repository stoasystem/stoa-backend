"""Where an account's rows live: its own partitions, and the ones it registered (#397).

Account deletion used to find a user's rows by scanning the whole table, because
most of them sit in partitions keyed by something else - a conversation, a
report, an upload - and say whose they are only in an attribute. This module is
the other half of that answer:

- **Derived partitions.** A fixed list of partition keys that are the user id
  behind a prefix (`USER#{id}`, `ATTEMPTS#{id}`, ...). Deletion queries each one
  directly; nothing is registered for them.
- **Registry rows.** For every other partition a write reaches - through
  `stoa.db.table.fenced`, or `stoa.db.table.registered` outside any fence -
  the same transaction puts one row under each account concerned:
  `USER#{id}/OWNS#{partition}` for the fence owner and for every account the
  data type catalog (`stoa.db.data_catalog`) says a written row is owned by,
  `USER#{id}/REFERENCED_IN#{partition}` for each `also=` account and every
  account a written row only mentions (a teacher on a help request). One row
  per partition, not per row, and the Put is unconditional and idempotent, so
  it cannot be forgotten and costs no read.

The catalog is the only answer to which accounts a row names (#589): a field
it lists as no pointer (`created_by`, `invited_by`, `actor_id`) registers
nobody, because no deletion acts on it (#586 decision 1). A Put's item says
how its row will stand; an Update that sets one of the catalog's pointer
paths has to say it too, by passing the row as it will stand (`rows=`), or
the write is refused before it is sent.

The role lives in the sort key, not in an attribute: two writes that register
the same partition for the same account in different roles keep both rows
instead of the later Put overwriting the earlier role.

Registry rows name the account only through their partition key and
`registry_account`, never `user_id` / `owner_id`: the deletion's predicates match
rows on those, and a registry row is bookkeeping, not the account's data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from stoa.db import data_catalog

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
    "LEARNING_MEMORY#",  # retired memory snapshots (#675); old rows are still deleted
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
    owner: str | None,
    references: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    *,
    rows: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """The registry Puts a write of `operations` carries.

    One per (account, role, partition):

    - `owner`, the fence owner of a fenced write, for every partition written
      that is not one of its own derived partitions, and each `references`
      account (the other fences) as a reference;
    - every account the data type catalog says a Put's item, or a row in
      `rows`, names, in the role the catalog gives it (`data_catalog.mentions`).

    `rows` are rows as they will stand after the write: the merged row of an
    Update, or a row the caller writes next by other means. An Update that
    sets a catalog pointer path (`updated_pointer_paths`) without its row in
    `rows` is a `ValueError`: what it does to whom the row names is not
    visible here. A key the operations themselves already touch is left out,
    so a transaction never names one item twice.
    """
    after = [dict(row) for row in rows]
    _require_rows_for_pointer_updates(operations, after)
    pairs: list[tuple[str, str, str]] = []
    if owner is not None:
        for partition in written_partitions(operations):
            pairs.append((owner, ROLE_OWNER, partition))
            pairs.extend((other, ROLE_REFERENCE, partition) for other in references)
    written: list[Mapping[str, Any]] = []
    for operation in operations:
        body = operation.get("Put") if isinstance(operation, Mapping) else None
        item = body.get("Item") if isinstance(body, Mapping) else None
        if isinstance(item, Mapping):
            written.append(item)
    for row in [*written, *after]:
        written_pk = row.get("PK")
        if not isinstance(written_pk, str) or not written_pk:
            continue
        for named, named_role in data_catalog.mentions(row).items():
            pairs.append((named, str(named_role), written_pk))
    taken = {_operation_key(operation) for operation in operations}
    wanted: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for account, role, partition in pairs:
        if is_derived_for(partition, account):
            continue
        item = registry_item(account, partition, role)
        key = (item["PK"], item["SK"])
        if key in seen or key in taken:
            continue
        seen.add(key)
        wanted.append({"Put": {"Item": item}})
    return wanted


_CLAUSE = re.compile(r"(?:^|(?<=\s))(SET|REMOVE|ADD|DELETE)(?=\s)", re.IGNORECASE)
_INDEX = re.compile(r"\[\d+\]")
_VALUE = re.compile(r"^:\w+$")
_IF_NOT_EXISTS = re.compile(r"^if_not_exists\(\s*([^,()]+?)\s*,\s*(:\w+)\s*\)$", re.IGNORECASE)


def _actions(update: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    """Each action of an Update: (SET / ADD / REMOVE / DELETE, path as written, path by name, rest)."""
    expression = update.get("UpdateExpression")
    if not isinstance(expression, str):
        return []
    names = update.get("ExpressionAttributeNames")
    aliases: Mapping[str, Any] = names if isinstance(names, Mapping) else {}
    clauses = _CLAUSE.split(expression)
    found: list[tuple[str, str, str, str]] = []
    for keyword, body in zip(clauses[1::2], clauses[2::2], strict=True):
        keyword = keyword.upper()
        for part in _top_level(body):
            if not part.strip():
                continue
            if keyword == "SET":
                if "=" not in part:
                    continue
                written, rest = part.split("=", 1)
            elif keyword in {"ADD", "DELETE"}:
                written, _, rest = part.strip().partition(" ")
            else:
                written, rest = part, ""
            written = written.strip()
            path = ".".join(str(aliases.get(name, name)) for name in written.split("."))
            found.append((keyword, written, path, rest.strip()))
    return found


def _is_pointer(path: str) -> bool:
    plain = _INDEX.sub("", path)
    return any(
        plain == pointer or pointer.startswith(f"{plain}.") or plain.startswith(f"{pointer}.")
        for pointer in data_catalog.POINTER_PATHS
    )


def updated_pointer_paths(update: Mapping[str, Any]) -> list[str]:
    """The catalog pointer paths an Update's `SET` / `ADD` can change, by name.

    A path is caught when it is a pointer path, lies inside one (an entry of
    `children`), or holds one (all of `metadata`). `REMOVE` and `DELETE` only
    take ids away, which leaves nothing new to register.
    """
    return [
        _INDEX.sub("", path)
        for keyword, _, path, _ in _actions(update)
        if keyword in {"SET", "ADD"} and _is_pointer(path)
    ]


def rows_after(
    row: Mapping[str, Any], operations: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """`row` as each Update of `operations` on its key will leave it, for `rows=`.

    `row` is the row as read (or just its key, for one the Update may create).
    Applies `SET path = :value`, `SET path = if_not_exists(path, :value)`,
    `ADD path :set` and `REMOVE path`, by name. Any other change to a pointer
    path (arithmetic, `list_append`, an index) is a `ValueError`: build that
    row by hand. Changes to other paths that cannot be worked out are left out,
    which the registry does not read.
    """
    key = (row.get("PK"), row.get("SK"))
    after: list[dict[str, Any]] = []
    for operation in operations:
        body = operation.get("Update") if isinstance(operation, Mapping) else None
        if not isinstance(body, Mapping):
            continue
        target = body.get("Key")
        if not isinstance(target, Mapping) or (target.get("PK"), target.get("SK")) != key:
            continue
        after.append(_apply(row, body))
    return after


def _apply(row: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    values = update.get("ExpressionAttributeValues")
    given: Mapping[str, Any] = values if isinstance(values, Mapping) else {}
    result: dict[str, Any] = _copy(row)
    for keyword, written, path, rest in _actions(update):
        names = path.split(".")
        plain = "[" not in path
        if keyword == "REMOVE":
            if plain:
                _remove(result, names)
            continue
        new: object = _UNKNOWN
        if keyword == "SET" and plain:
            if _VALUE.match(rest) and rest in given:
                new = given[rest]
            else:
                match = _IF_NOT_EXISTS.match(rest)
                if match and match.group(1).strip() == written and match.group(2) in given:
                    current = _get(result, names)
                    new = given[match.group(2)] if current is None else current
        elif keyword == "ADD" and plain and _VALUE.match(rest) and rest in given:
            current, extra = _get(result, names), given[rest]
            if isinstance(extra, (set, frozenset)):
                new = set(current or ()) | set(extra)
            elif isinstance(extra, (int, float)) and not isinstance(extra, bool):
                new = (current or 0) + extra
        elif keyword == "DELETE":
            continue
        if new is _UNKNOWN:
            if _is_pointer(path):
                raise ValueError(f"cannot work out how the Update leaves {path}; pass the row by hand")
            continue
        _set(result, names, new)
    return result


_UNKNOWN = object()


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {name: _copy(child) for name, child in value.items()}
    return value


def _get(row: Mapping[str, Any], names: list[str]) -> Any:
    value: Any = row
    for name in names:
        if not isinstance(value, Mapping):
            return None
        value = value.get(name)
    return value


def _set(row: dict[str, Any], names: list[str], value: Any) -> None:
    holder = row
    for name in names[:-1]:
        child = holder.get(name)
        if not isinstance(child, dict):
            child = {}
            holder[name] = child
        holder = child
    holder[names[-1]] = value


def _remove(row: dict[str, Any], names: list[str]) -> None:
    holder: Any = row
    for name in names[:-1]:
        holder = holder.get(name) if isinstance(holder, dict) else None
    if isinstance(holder, dict):
        holder.pop(names[-1], None)


def _top_level(body: str) -> list[str]:
    """`body` split at the commas outside any parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in body:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    parts.append("".join(current))
    return parts


def _require_rows_for_pointer_updates(
    operations: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> None:
    given = {(row.get("PK"), row.get("SK")) for row in rows}
    for operation in operations:
        body = operation.get("Update") if isinstance(operation, Mapping) else None
        if not isinstance(body, Mapping):
            continue
        changed = updated_pointer_paths(body)
        if not changed:
            continue
        key = body.get("Key")
        if not isinstance(key, Mapping) or (key.get("PK"), key.get("SK")) not in given:
            raise ValueError(
                f"an Update that sets {sorted(set(changed))} must pass its row as it "
                "will stand (rows=), so the owner registry sees whom it names (#589)"
            )


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
