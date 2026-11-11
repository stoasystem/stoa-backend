"""The table gateway: the one place a transaction is serialized, sent and judged.

Four writers used to do this each in their own way (#210). They disagreed on which
`None` values to leave out, guessed the region when they built a client, and two of
them read DynamoDB's cancellation reasons with rules that had drifted apart. Here
there is one of each:

- `table()` and `client()`: the table every repository uses and the low-level client
  a transaction is sent on, each built once, in the configured region.
- `get` / `put` / `update` / `delete`: one item, in the table's own request shape.
  The answer is checked once, here; a write whose condition does not hold is
  `WriteRefused`, never a provider error string for each caller to match.
- `transact(operations)`: operations in the repositories' own shape - plain Python
  values, no `TableName` - serialized once, sent once. `Item`, `Key` and
  `ExpressionAttributeValues` lose their `None` members, always.
- `fenced(owner, operations)`: the same, behind the owner's account fence - the
  fence read, its condition put in front, a refused fence reported as the account
  not being writable rather than as the caller's own operations failing.
- `pages("query" | "scan", ...)`: a read that goes on past the table's page, page
  by page. Each continuation key is checked once, here, and a read that stops
  moving forward is reported instead of looping. `page_token(scope, position)` and
  `read_page_token(token, scope)` are the one opaque form a position leaves the
  service in; a token only continues the listing it was made for.
- Two outcomes besides success. `WriteRefused`: the table read the write and
  turned it down, and - for a transaction - says why for each operation. `TableUnavailable`: the table
  could not be asked, or did not answer in a shape that says anything. A repository
  that has to tell causes apart translates these into its own domain's errors; one
  that does not lets them through.

A test double takes part by offering `transact_write_items(TransactItems=...)` and
receiving exactly what the real client would: wire format, `TableName` included.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import lru_cache
from itertools import islice
from typing import Any, Literal, cast

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError

from stoa import config
from stoa.db import owner_registry

logger = logging.getLogger(__name__)

type Operation = Mapping[str, Any]

TRANSACTION_ACTIONS = frozenset({"ConditionCheck", "Put", "Update", "Delete"})
_VALUE_FIELDS = ("Item", "Key", "ExpressionAttributeValues")


# -- the table and the client ---------------------------------------------------------

_installed: object | None = None


@lru_cache
def _real_table() -> object:
    return boto3.resource("dynamodb", region_name=config.settings().aws_region).Table(
        config.settings().dynamodb_table_name
    )


def table() -> object:
    """The table: the one `install` was given, or else the real one."""
    return _installed if _installed is not None else _real_table()


def install(double: object | None) -> None:
    """Put `double` where the real table would be; `None` takes it away again.

    The suite's one installation point: the `fake_table` fixture installs a
    `FakeTable` here, and every test starts with an empty one. Patches of a
    module's own `get_table` still win over it, until the batches of #210 that
    move each domain onto the gateway remove them.
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
    return boto3.client("dynamodb", region_name=config.settings().aws_region)


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

    @property
    def condition_failed(self) -> bool:
        """Whether a condition the caller wrote is what turned the write down.

        A transaction says so per operation. A single conditional write names no
        operation, and has nothing but its condition to be refused for.
        """
        if self.reasons:
            return bool(self.failed_conditions)
        return self.code == "ConditionalCheckFailedException"


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
    table_name = name if isinstance(name, str) and name else config.settings().dynamodb_table_name
    items = [_serialize(operation, table_name) for operation in given]
    try:
        execute(TransactItems=items)
    except ClientError as exc:
        raise _judged(exc, given) from exc
    except BotoCoreError as exc:
        logger.warning("table_unavailable code=%s", type(exc).__name__)
        raise TableUnavailable(type(exc).__name__) from exc


# -- one item ---------------------------------------------------------------------------


def get(*, table: object | None = None, **request: object) -> dict[str, Any] | None:
    """The item `Key` names, or `None` when the table holds none.

    `request` is what the table's own `get_item` takes. The table's own errors
    pass through untouched, as a paged read's do. An answer that is not an item
    is `TableUnavailable("malformed_response")`.
    """
    response = _entry(table, "get_item")(**request)
    if not isinstance(response, Mapping):
        raise TableUnavailable("malformed_response")
    return _attributes(response.get("Item"), absent=None)


def put(*, table: object | None = None, **request: object) -> dict[str, Any]:
    """Write one item: `request` is what the table's own `put_item` takes.

    Returns the attributes the write hands back (`ReturnValues`), `{}` when it
    hands back none. A condition that does not hold is `WriteRefused`; anything
    else the table answers is `TableUnavailable`. Values are sent as given: a
    single write is not a transaction, and keeps its own rules about `None`.
    """
    return _write("Put", "put_item", request, table)


def update(*, table: object | None = None, **request: object) -> dict[str, Any]:
    """Update one item: `request` is what the table's own `update_item` takes.

    Outcomes as for `put`.
    """
    return _write("Update", "update_item", request, table)


def delete(*, table: object | None = None, **request: object) -> dict[str, Any]:
    """Delete one item: `request` is what the table's own `delete_item` takes.

    Outcomes as for `put`.
    """
    return _write("Delete", "delete_item", request, table)


def _entry(table: object | None, method: str) -> Callable[..., object]:
    target = table if table is not None else _installed if _installed is not None else _real_table()
    call = getattr(target, method, None)
    if not callable(call):
        raise TableUnavailable(f"no_{method}_entry")
    return call


def _write(
    action: str, method: str, request: dict[str, object], table: object | None
) -> dict[str, Any]:
    call = _entry(table, method)
    try:
        response = call(**request)
    except ClientError as exc:
        raise _judged(exc, [{action: request}]) from exc
    except BotoCoreError as exc:
        logger.warning("table_unavailable code=%s", type(exc).__name__)
        raise TableUnavailable(type(exc).__name__) from exc
    if response is None:
        # A double with nothing to hand back may return nothing at all.
        return {}
    if not isinstance(response, Mapping):
        raise TableUnavailable("malformed_response")
    return _attributes(response.get("Attributes"), absent={})


def _attributes[T](value: object, *, absent: T) -> dict[str, Any] | T:
    if value is None:
        return absent
    if not isinstance(value, Mapping) or not all(isinstance(name, str) for name in value):
        raise TableUnavailable("malformed_response")
    return dict(value)


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

    The write also registers where it went (#397): for every partition a Put
    or Update touches that is not one of the account's own derived partitions,
    an unconditional Put of `USER#{owner}/OWNS#{partition}` (and of
    `USER#{other}/REFERENCED_IN#{partition}` for each `also=` account), in
    the same transaction - see `stoa.db.owner_registry`. Every account a Put's
    row names the way deletion's matcher reads it (a notification's actor, a
    grant's `student:` scope) is registered the same way, owner or reference. When that would take
    the transaction past DynamoDB's 100 items, the registry rows are committed
    first, behind the same fences, and the caller's operations after.

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
    registry = owner_registry.registry_operations(
        owner, list(also or {}), own, mentions=fences.mentioned_accounts
    )
    if len(conditions) + len(own) + len(registry) <= TRANSACTION_ITEM_LIMIT:
        own_and_registry = [*own, *registry]
    else:
        # Too many for one transaction: register first, under the same fences.
        # A registry row for a partition the write then never reaches is
        # harmless - the deletion finds nothing there - while a write without
        # its registry row is the one thing the registry must not allow.
        _register_ahead(conditions, registry, table=table)
        own_and_registry = own
    try:
        transact([*conditions, *own_and_registry], table=table)
    except WriteRefused as exc:
        fence_reasons = exc.reasons[: len(conditions)]
        own_reasons = exc.reasons[len(conditions) : len(conditions) + len(own)]
        registry_reasons = exc.reasons[len(conditions) + len(own) :]
        kinds = {reason.kind for reason in fence_reasons}
        if ReasonKind.CONDITION_FAILED in kinds:
            raise fences.AccountNotWritable("account is not writable") from exc
        if (kinds | {reason.kind for reason in registry_reasons}) - {ReasonKind.NOT_THE_CAUSE}:
            # The fence row or a registry row was busy or throttled: the
            # caller's reasons alone would say nothing went wrong with its
            # operations.
            own_reasons = ()
        raise WriteRefused(exc.code, own_reasons) from exc


# DynamoDB's limit on the items of one transaction.
TRANSACTION_ITEM_LIMIT = 100


def _register_ahead(
    conditions: list[Operation], registry: list[Operation], *, table: object | None
) -> None:
    """Commit `registry` behind `conditions`, in as many transactions as it takes."""
    room = TRANSACTION_ITEM_LIMIT - len(conditions)
    if room <= 0:
        raise ValueError("too many fences for one transaction")
    fences = _account_fences()
    for start in range(0, len(registry), room):
        try:
            transact([*conditions, *registry[start : start + room]], table=table)
        except WriteRefused as exc:
            if ReasonKind.CONDITION_FAILED in {
                reason.kind for reason in exc.reasons[: len(conditions)]
            }:
                raise fences.AccountNotWritable("account is not writable") from exc
            raise WriteRefused(exc.code, ()) from exc


# -- reading page by page -------------------------------------------------------------

# Far more pages than this table has; a reader that needs more has a filter that
# is not doing its job, and should say so rather than read the account.
SCAN_PAGE_BUDGET = 200

# The base table's key. A read on an index continues from that index's key as
# well, and names it: `key=("PK", "SK", "parent_id", "week_start")`.
BASE_KEY = ("PK", "SK")

type Position = dict[str, Any]


class PageTokenInvalid(ValueError):
    """A page token, or a stored start key, that no read can continue from.

    Forged, damaged, made for another listing, or written before #298 changed
    the format: the caller cannot tell these apart and need not - the listing
    starts again from its first page.
    """


@dataclass(frozen=True, slots=True)
class Page:
    """One page of a read: its rows, and where the next page starts.

    `last_key` is `None` on the last page. It is the key as the table gave it,
    already checked; a sweep that stores it can hand it back as `start`.
    """

    items: list[dict[str, Any]]
    last_key: Position | None
    scope: str | None = None

    @property
    def next_token(self) -> str | None:
        """Where the next page starts, as a token for this page's listing."""
        if self.last_key is None:
            return None
        if self.scope is None:
            raise ValueError("a read made without a scope hands out no token")
        return page_token(self.scope, self.last_key)


def pages(
    read: Literal["query", "scan"],
    /,
    *,
    start: Mapping[str, object] | None = None,
    token: str | None = None,
    scope: str | None = None,
    within: Callable[[Position], bool] | None = None,
    key: Sequence[str] = BASE_KEY,
    table: object | None = None,
    **request: object,
) -> Iterator[Page]:
    """The pages of one query or scan, in order, until the table has no more.

    `request` is what the table's own `query` / `scan` takes, without
    `ExclusiveStartKey`: a read starts at the beginning, at `start` (a key a sweep
    kept from an earlier `Page.last_key`), or at `token` (from `Page.next_token`,
    read against `scope`, and - when `within` is given - only if the position it
    holds belongs to this listing). A start that cannot be read raises
    `PageTokenInvalid` here, before anything is asked of the table.

    Mechanics only. How many pages to take is the caller's (`itertools.islice`),
    and so is a sweep's rule about a cursor coming round again: a sweep that
    stores its place decides for itself what a repeated key means (#298). What
    is checked here, once: every continuation key has exactly the attributes in
    `key`, each a non-empty string or a number, or the read is
    `TableUnavailable("malformed_page_key")`; a response that is not a page is
    `TableUnavailable("malformed_page")`. The table's own errors pass through
    untouched.
    """
    if read not in ("query", "scan"):
        raise ValueError(f"not a paged read: {read}")
    if "ExclusiveStartKey" in request:
        raise ValueError("start a paged read with `start` or `token`")
    if token is not None and start is not None:
        raise ValueError("a read starts at a token or at a key, not both")
    if token is not None:
        if scope is None:
            raise ValueError("a token is read against the listing it was made for")
        current: Position | None = read_page_token(token, scope, key=key, within=within)
    elif start is not None:
        current = page_key(start, key=key)
    else:
        current = None
    target = table if table is not None else _installed if _installed is not None else _real_table()
    call = getattr(target, read, None)
    if not callable(call):
        raise TableUnavailable(f"no_{read}_entry")
    return _walk(call, dict(request), current, tuple(key), scope)


def _walk(
    call: Callable[..., object],
    request: dict[str, object],
    current: Position | None,
    key: tuple[str, ...],
    scope: str | None,
) -> Iterator[Page]:
    while True:
        if current is not None:
            request["ExclusiveStartKey"] = current
        response = call(**request)
        if not isinstance(response, Mapping):
            raise TableUnavailable("malformed_page")
        raw_items = response.get("Items", [])
        if not isinstance(raw_items, list) or not all(
            isinstance(item, Mapping) for item in raw_items
        ):
            raise TableUnavailable("malformed_page")
        items = [dict(item) for item in raw_items]
        raw_key = response.get("LastEvaluatedKey")
        # No key, or an empty one, is the end of the read: DynamoDB allows both.
        if raw_key is None or (isinstance(raw_key, Mapping) and not raw_key):
            yield Page(items, None, scope)
            return
        try:
            next_key = page_key(raw_key, key=key)
        except PageTokenInvalid:
            raise TableUnavailable("malformed_page_key") from None
        yield Page(items, next_key, scope)
        current = next_key


def rows(
    read: Literal["query", "scan"],
    /,
    *,
    want: int | None = None,
    page_budget: int = SCAN_PAGE_BUDGET,
    key: Sequence[str] = BASE_KEY,
    table: object | None = None,
    **request: object,
) -> list[dict[str, Any]]:
    """Every row a filtered read admits, across the table's pages.

    `Limit` bounds the rows a read *looks at*, not the rows its filter keeps, so a
    scan with `Limit=100` answers from the first hundred rows of the table and
    returns whichever of them matched. On a table larger than the thing being
    looked for that is nothing, and nothing says so - a teacher's help request
    was invisible in production for exactly this reason (#95). So `Limit` is not
    taken here; `want` caps the rows kept, which is what those callers meant.

    A page that hands back the key it started from has not moved:
    `TableUnavailable("page_did_not_advance")` rather than a loop. A read that
    has not ended after `page_budget` pages is `TableUnavailable("page_budget_spent")`:
    an answer from part of the table would look like an answer.
    """
    if "Limit" in request:
        raise ValueError("`Limit` counts rows read, not rows kept: pass `want`")
    found: list[dict[str, Any]] = []
    started_at: Position | None = None
    for page in islice(pages(read, key=key, table=table, **request), page_budget):
        found.extend(page.items)
        if want is not None and len(found) >= want:
            return found[:want]
        if page.last_key is None:
            return found
        if page.last_key == started_at:
            raise TableUnavailable("page_did_not_advance")
        started_at = page.last_key
    raise TableUnavailable("page_budget_spent")


def page_key(value: object, *, key: Sequence[str] = BASE_KEY) -> Position:
    """`value` as a key a read can continue from, or `PageTokenInvalid`.

    Exactly the attributes in `key`, each a non-empty string or a finite number.
    """
    if (
        not isinstance(value, Mapping)
        or set(value) != set(key)
        or len(value) != len(key)
        or not all(_key_member(value[name]) for name in key)
    ):
        raise PageTokenInvalid("not a key this read can continue from")
    return {name: value[name] for name in key}


def _key_member(value: object) -> bool:
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    return isinstance(value, int)


# A token is `2.` and the URL-safe base64 of `{"s": scope, "p": position}`, with
# numbers written as `{"N": "<digits>"}` so a `Decimal` comes back a `Decimal`.
# Base64 has no `.`, so a token from before this format can never be read as one.
_TOKEN_PREFIX = "2."
_TOKEN_LIMIT = 2048


def page_token(scope: str, position: Mapping[str, object]) -> str:
    """`position` as an opaque token that only `read_page_token(..., scope)` reads.

    `scope` names the listing, and the partition when the listing is one: a
    token made for one report's audit timeline does not continue another's.
    A position is a key or anything else a listing resumes from (the last
    case handed out, say): names to strings or numbers.
    """
    if not isinstance(scope, str) or not scope or not position:
        raise ValueError("a page token holds a position within a named listing")
    encoded: dict[str, object] = {}
    for name, value in position.items():
        if isinstance(value, str):
            encoded[name] = value
        elif isinstance(value, (int, Decimal)) and not isinstance(value, bool):
            encoded[name] = {"N": str(value)}
        else:
            raise ValueError("a page token holds strings and numbers")
    raw = json.dumps({"s": scope, "p": encoded}, separators=(",", ":"), sort_keys=True)
    token = _TOKEN_PREFIX + base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    if len(token) > _TOKEN_LIMIT:
        raise ValueError("a position this large does not belong in a page token")
    return token


def read_page_token(
    token: object,
    scope: str,
    *,
    key: Sequence[str] | None = None,
    within: Callable[[Position], bool] | None = None,
) -> Position:
    """The position `token` holds, or `PageTokenInvalid`.

    The token must be one `page_token` made for `scope`. With `key`, the position
    must be a key with exactly those attributes; with `within`, the position must
    satisfy it - the check that a key from a hand-made token still lies inside the
    partition being read, which the table would otherwise refuse as a request.
    """
    if not isinstance(token, str) or not token.startswith(_TOKEN_PREFIX) or len(token) > _TOKEN_LIMIT:
        raise PageTokenInvalid("not a page token")
    body = token[len(_TOKEN_PREFIX) :]
    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise PageTokenInvalid("not a page token") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"s", "p"}
        or payload["s"] != scope
        or not isinstance(payload["p"], dict)
        or not payload["p"]
    ):
        raise PageTokenInvalid("not a token for this listing")
    position: Position = {}
    for name, value in payload["p"].items():
        if isinstance(value, str):
            position[name] = value
            continue
        if not isinstance(value, dict) or set(value) != {"N"} or not isinstance(value["N"], str):
            raise PageTokenInvalid("not a page token")
        try:
            number = Decimal(value["N"])
        except InvalidOperation:
            raise PageTokenInvalid("not a page token") from None
        if not number.is_finite():
            raise PageTokenInvalid("not a page token")
        position[name] = number
    if key is not None:
        position = page_key(position, key=key)
    if within is not None and not within(position):
        raise PageTokenInvalid("not a token for this listing")
    return position


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
