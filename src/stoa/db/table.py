"""The table gateway: the one place a transaction is serialized, sent and judged.

Four writers used to do this each in their own way (#210). They disagreed on which
`None` values to leave out, guessed the region when they built a client, and two of
them read DynamoDB's cancellation reasons with rules that had drifted apart. Here
there is one of each:

- `table()` and `client()`: the table every repository uses and the low-level client
  a transaction is sent on, each built once, in the configured region.
- `transact(operations)`: operations in the repositories' own shape - plain Python
  values, no `TableName` - serialized once, sent once. `Item`, `Key` and
  `ExpressionAttributeValues` lose their `None` members, always.
- `fenced(owner, operations)`: the same, behind the owner's account fence - the
  fence read, its condition put in front, a refused fence reported as the account
  not being writable rather than as the caller's own operations failing.
- Two outcomes besides success. `WriteRefused`: the table read the transaction and
  turned it down, and says why for each operation. `TableUnavailable`: the table
  could not be asked, or did not answer in a shape that says anything. A repository
  that has to tell causes apart translates these into its own domain's errors; one
  that does not lets them through.

A test double takes part by offering `transact_write_items(TransactItems=...)` and
receiving exactly what the real client would: wire format, `TableName` included.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any, cast

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError

from stoa.config import settings

logger = logging.getLogger(__name__)

type Operation = Mapping[str, Any]

TRANSACTION_ACTIONS = frozenset({"ConditionCheck", "Put", "Update", "Delete"})
_VALUE_FIELDS = ("Item", "Key", "ExpressionAttributeValues")


# -- the table and the client ---------------------------------------------------------

_installed: object | None = None


@lru_cache
def _real_table() -> object:
    return boto3.resource("dynamodb", region_name=settings.aws_region).Table(
        settings.dynamodb_table_name
    )


def table() -> object:
    """The table: the one `install` was given, or else the real one."""
    return _installed if _installed is not None else _real_table()


def install(double: object | None) -> None:
    """Put `double` where the real table would be; `None` takes it away again.

    The suite does not use this yet - it patches each module's `get_table` - and
    moves onto it with the paging step of #210.
    """
    global _installed
    _installed = double


@lru_cache
def client() -> Any:
    """A low-level client of the gateway's own, never the resource's `meta.client`.

    The resource registers request transformations on its client, and items that
    are already in wire format come back out of them mangled - every key turned
    into a map, every condition check answered `ValidationError`. Each writer that
    once used the resource's client learned this separately; this is the only
    place it now has to be known.
    """
    return boto3.client("dynamodb", region_name=settings.aws_region)


def transactional(target: object) -> bool:
    """Whether `target` can run a transaction at all.

    The real table can, and so can a double offering `transact_write_items`. A
    lighter double cannot hold the account fence a transaction would check, and a
    few repositories still fall back to a plain write for it.
    """
    return callable(getattr(target, "transact_write_items", None)) or bool(
        getattr(getattr(target, "meta", None), "client", None)
        and getattr(target, "name", None)
    )


# -- outcomes ---------------------------------------------------------------------------


class ReasonKind(StrEnum):
    """What one operation's cancellation reason says about it."""

    NOT_THE_CAUSE = "not_the_cause"
    CONDITION_FAILED = "condition_failed"
    TRANSACTION_CONFLICT = "transaction_conflict"
    RETRYABLE = "retryable"
    OTHER = "other"


# Capacity, not the request: the same transaction can go through a moment later.
RETRYABLE_REASON_CODES = frozenset({"ProvisionedThroughputExceeded", "ThrottlingError"})


def classify_reason(code: object) -> ReasonKind:
    """One cancellation reason code, sorted.

    `OTHER` is everything that is not named above it: `ValidationError` and
    `ItemCollectionSizeLimitExceeded`, which say this request can never succeed as
    sent, and any code DynamoDB adds later. It is deliberately not `RETRYABLE` -
    nothing here knows that waiting would help - and a caller that still chooses to
    let the client retry decides that for itself (#271).
    """
    if code == "None":
        return ReasonKind.NOT_THE_CAUSE
    if code == "ConditionalCheckFailed":
        return ReasonKind.CONDITION_FAILED
    if code == "TransactionConflict":
        return ReasonKind.TRANSACTION_CONFLICT
    if code in RETRYABLE_REASON_CODES:
        return ReasonKind.RETRYABLE
    return ReasonKind.OTHER


@dataclass(frozen=True, slots=True)
class CancellationReason:
    """The table's own code for one operation, and what it means."""

    code: str
    kind: ReasonKind


def cancellation_reasons(
    response: Mapping[str, object], operation_count: int
) -> tuple[CancellationReason, ...]:
    """One reason per operation, in order - or none, when the table did not give that.

    A missing list, or one whose length is not the transaction's, cannot be lined
    up with the operations, so nothing is read from it. An entry without a string
    code is `OTHER`: it is a reason nobody can name.
    """
    raw = response.get("CancellationReasons")
    if not isinstance(raw, list) or len(raw) != operation_count:
        return ()
    reasons = []
    for entry in raw:
        code = entry.get("Code") if isinstance(entry, Mapping) else None
        if not isinstance(code, str):
            reasons.append(CancellationReason("<unreadable>", ReasonKind.OTHER))
        else:
            reasons.append(CancellationReason(code, classify_reason(code)))
    return tuple(reasons)


class WriteRefused(RuntimeError):
    """The table read the transaction and refused it. Nothing in it was written.

    `reasons` holds one entry per operation, in the order they were given, or is
    empty when the table did not say (a single conditional write, or a
    cancellation whose reasons could not be read).
    """

    def __init__(self, code: str, reasons: Sequence[CancellationReason] = ()) -> None:
        super().__init__(f"write refused: {code}")
        self.code = code
        self.reasons = tuple(reasons)

    @property
    def failed_conditions(self) -> tuple[int, ...]:
        """The positions of the operations whose condition did not hold."""
        return tuple(
            index
            for index, reason in enumerate(self.reasons)
            if reason.kind is ReasonKind.CONDITION_FAILED
        )

    @property
    def causes(self) -> frozenset[ReasonKind]:
        """Every kind of reason that took part in the refusal."""
        return frozenset(
            reason.kind
            for reason in self.reasons
            if reason.kind is not ReasonKind.NOT_THE_CAUSE
        )


class TableUnavailable(RuntimeError):
    """The table could not be asked, or its answer said nothing about the write.

    `code` is the provider's error code when there was one. A refused request
    (`ValidationException`) lands here too: the table did not decide on the write,
    the request never got that far.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"table unavailable: {code}")
        self.code = code


# -- the one transaction --------------------------------------------------------------

_serializer = TypeSerializer()


def transact(operations: Iterable[Operation], *, table: object | None = None) -> None:
    """Commit `operations` as one transaction, or raise `WriteRefused` / `TableUnavailable`.

    `table` is a double standing in for the real table; it takes the wire format
    through `transact_write_items`. Any other exception a double raises is passed on
    untouched.
    """
    given = list(operations)
    if table is not None:
        target = table
    else:
        target = _installed if _installed is not None else _real_table()
    execute = getattr(target, "transact_write_items", None)
    name = getattr(target, "name", None)
    if not callable(execute):
        if not isinstance(name, str) or not name:
            raise TableUnavailable("no_transaction_entry")
        execute = client().transact_write_items
    table_name = name if isinstance(name, str) and name else settings.dynamodb_table_name
    items = [_serialize(operation, table_name) for operation in given]
    try:
        execute(TransactItems=items)
    except ClientError as exc:
        raise _judged(exc, given) from exc
    except BotoCoreError as exc:
        logger.warning("table_unavailable code=%s", type(exc).__name__)
        raise TableUnavailable(type(exc).__name__) from exc


# -- a write behind an account's fence ------------------------------------------------

type Operations = Iterable[Operation] | Callable[[int], Iterable[Operation]]


def fenced(
    owner: str,
    operations: Operations,
    *,
    generation: int | None = None,
    any_generation: bool = False,
    also: Mapping[str, int | None] | None = None,
    table: object | None = None,
) -> None:
    """Commit `operations` only while `owner`'s account fence is active.

    Every private write is made behind the fence its owner's account deletion
    flips, so a write and a deletion cannot both win. A caller names the owner and
    its own operations; this reads the fence, puts its condition in front of them
    and sends the transaction.

    - `generation`: the fence generation the caller already holds (stamped on a
      row it read, or read earlier in the same request). The fence is then not
      read again: the condition alone says whether it still holds.
    - `any_generation`: neither read the fence nor hold it to a generation; the
      condition asks only that it be active. For a best-effort write that must
      not cost a read of its own (the sign-in time stamp).
    - `operations` may be a function of the generation, for rows that carry it.
    - `also`: other accounts whose fences must hold in the same transaction,
      each with its generation or `None` to read it.

    Outcomes besides success: `AccountNotWritable` (an `AccountDeletionConflict`)
    when a fence is missing, not active or not the expected generation - whether
    the read said so or the transaction did. `WriteRefused` when the caller's own
    operations were refused; its `reasons` line up with them, the fence checks
    taken out, and are empty when they cannot be told apart. `TableUnavailable`
    as from `transact`.
    """
    fences = _account_fences()
    if any_generation and (generation is not None or callable(operations)):
        raise ValueError("a write under any generation neither holds nor stamps one")
    owners = {owner: generation, **(also or {})}
    if len(owners) != 1 + len(also or {}):
        raise ValueError("an account's fence can be held only once in a transaction")
    generations: dict[str, int | None] = {
        account: known
        if known is not None or (account == owner and any_generation)
        else int(fences.require_active_account_fence(account, table=table)["generation"])
        for account, known in owners.items()
    }
    own = list(operations(cast(int, generations[owner])) if callable(operations) else operations)
    conditions = [
        fences.active_fence_condition(account, held) for account, held in generations.items()
    ]
    try:
        transact([*conditions, *own], table=table)
    except WriteRefused as exc:
        fence_reasons, own_reasons = exc.reasons[: len(conditions)], exc.reasons[len(conditions) :]
        kinds = {reason.kind for reason in fence_reasons}
        if ReasonKind.CONDITION_FAILED in kinds:
            raise fences.AccountNotWritable("account is not writable") from exc
        if kinds - {ReasonKind.NOT_THE_CAUSE}:
            # The fence row itself was busy or throttled: the caller's reasons
            # alone would say nothing went wrong with its operations.
            own_reasons = ()
        raise WriteRefused(exc.code, own_reasons) from exc


def _account_fences() -> Any:
    """The account fence's row, condition, read and conflict.

    They belong to the account deletion flow, which writes through this module,
    so it is imported when a fenced write first needs it.
    """
    from stoa.db.repositories import account_deletion_repo

    return account_deletion_repo


def _serialize(operation: Operation, table_name: str) -> dict[str, object]:
    if not isinstance(operation, Mapping) or len(operation) != 1:
        raise ValueError("a transaction operation names exactly one action")
    ((action, body),) = operation.items()
    if action not in TRANSACTION_ACTIONS or not isinstance(body, Mapping):
        raise ValueError(f"unsupported transaction operation: {action}")
    wire: dict[str, object] = {}
    for field, value in body.items():
        if field in _VALUE_FIELDS:
            if not isinstance(value, Mapping):
                raise ValueError(f"{action}.{field} must be a mapping")
            wire[field] = {
                name: _serializer.serialize(member)
                for name, member in value.items()
                if member is not None
            }
        else:
            wire[field] = value
    wire["TableName"] = table_name
    return {action: wire}


def _judged(exc: ClientError, operations: list[Operation]) -> WriteRefused | TableUnavailable:
    response = exc.response
    code = str(response.get("Error", {}).get("Code") or "unknown")
    if code == "TransactionCanceledException":
        reasons = cancellation_reasons(response, len(operations))
        # DynamoDB names the operation that refused; losing it leaves a caller
        # with a conflict nobody can act on or diagnose.
        logger.warning(
            "transaction_refused reasons=%s",
            [
                f"{index}:{reason.code}"
                for index, reason in enumerate(reasons)
                if reason.kind is not ReasonKind.NOT_THE_CAUSE
            ]
            or "unreadable",
        )
        if ReasonKind.OTHER in {reason.kind for reason in reasons}:
            # A reason that waiting will not fix: say so where someone will read it.
            logger.error("transaction_refused_for_good %s", transaction_shape(operations))
        return WriteRefused(code, reasons)
    if code == "ConditionalCheckFailedException":
        logger.info("write_refused code=%s", code)
        return WriteRefused(code)
    if code == "ValidationException":
        # The request was malformed, not refused: no retry fixes it and no
        # condition explains it, so the shape is the only thing that can.
        logger.error(
            "transaction_rejected %s rule=%s",
            transaction_shape(operations),
            safe_validation_message(exc),
        )
    else:
        logger.warning("table_unavailable code=%s", code)
    return TableUnavailable(code)


# -- what may be written down about a refused request ---------------------------------

_IDENTIFIER = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b|\b[0-9a-fA-F]{16,}\b")


def safe_validation_message(exc: ClientError) -> str:
    """The rule DynamoDB says was broken, with anything id-shaped taken out.

    These messages name attributes and expression tokens, not the rows' values,
    but a message is still the provider's words - so UUIDs and long hex runs
    are replaced before it is written down, and the rest is bounded.
    """
    message = str(exc.response.get("Error", {}).get("Message") or "")
    return _IDENTIFIER.sub("<id>", message)[:240]


def transaction_shape(operations: Sequence[object]) -> str:
    """Describe a transaction by shape alone: no values, no identifiers.

    A `ValidationException` says the request itself was malformed, and the
    structural rules it enforces - one operation per item, at most a hundred
    items, well-formed keys - are all answerable from the shape. Keys are reduced
    to their prefix before the first `#`, so what is logged is
    `Put:ATTACHMENT/META`, never whose attachment it is.
    """
    parts: list[str] = []
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for entry in operations:
        if not isinstance(entry, Mapping):
            parts.append("?")
            continue
        for kind, body in entry.items():
            if not isinstance(body, Mapping):
                continue
            key = body.get("Key") or body.get("Item") or {}
            pk = str(key.get("PK", "")) if isinstance(key, Mapping) else ""
            sk = str(key.get("SK", "")) if isinstance(key, Mapping) else ""
            if (pk, sk) in seen:
                duplicates += 1
            seen.add((pk, sk))
            parts.append(f"{kind}:{pk.split('#')[0] or '?'}/{sk.split('#')[0] or '?'}")
    return f"items={len(operations)} duplicate_keys={duplicates} shape=[{' '.join(parts)}]"
