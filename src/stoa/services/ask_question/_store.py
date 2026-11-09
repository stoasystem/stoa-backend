"""The rows a question keeps while it is answered: its command, lease and settlement.

Moved from `attachment_repo` (#217, step 1 of #204). The command row, the AI
lease, the provider records, the generation progress and the settlement of the
quota reservation are the question's own; attachment and conversation rows stay
in `attachment_repo`, which this module still writes through for the shared
transaction, key and scrub helpers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import islice

from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo


class MessageCommandDisposition(StrEnum):
    """Closed durable outcomes for every message-command transition."""

    CLAIMED = "claimed"
    RESUME = "resume"
    COMPLETED = "completed"
    REJECTED = "rejected"
    QUOTA_EXCEEDED = "quota_exceeded"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RETRYABLE = "retryable"
    LEASE_HELD = "lease_held"
    TERMINAL = "terminal"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class MessageCommandResult:
    disposition: MessageCommandDisposition
    command: dict[str, object] | None = None
    counter_value: int | None = None
    error_code: str | None = None
    attempt: int | None = None
    operations: tuple[attachment_repo.TransactionOperation, ...] = ()
    # On a claimed AI lease: the status the command had just before the claim,
    # which tells a lease that ran out from an attempt that ended on its own.
    previous_status: str | None = None


# A generation is tried this many times under one command, whichever way the
# earlier attempts ended.
MESSAGE_AI_MAX_ATTEMPTS = 3


# What `fail_message_command` writes and the next lease claim clears.
MESSAGE_FAILURE_FIELDS = ("failure_category", "failure_retryable", "failed_at")


# What an attempt leaves while its outcome is not settled: the mark that it
# called the model, and the answer it kept. Completion and a recorded failure
# settle the outcome and clear them, so a mark still present always means a
# call nobody has accounted for.
MESSAGE_ATTEMPT_TRACE_FIELDS = (
    "provider_invoked_attempt",
    "provider_result_attempt",
    "provider_result_json",
)


def message_command_key(conversation_id: str, idempotency_key: str) -> dict[str, str]:
    return {
        "PK": f"CONV#{conversation_id}",
        "SK": f"MESSAGE_COMMAND#{idempotency_key}",
    }


def chat_quota_key(owner_id: str, quota_period: str) -> dict[str, str]:
    return {"PK": f"USAGE#{owner_id}", "SK": f"CHAT#{quota_period}"}


def chat_quota_operation_key(owner_id: str, command_id: str) -> dict[str, str]:
    return {"PK": f"USAGE#{owner_id}", "SK": f"CHAT_QUOTA_OP#{command_id}"}


def generation_progress_key(conversation_id: str) -> dict[str, str]:
    return {"PK": f"CONV#{conversation_id}", "SK": "GENERATION"}


def record_generation_progress(
    conversation_id: str,
    *,
    owner_id: str,
    steps: list[str],
    now_iso: str,
    expires_at: int,
    command_id: str | None = None,
    attempt: int | None = None,
    table: object | None = None,
) -> bool:
    """Publish the steps of an answer still being written.

    The request that generates an answer holds its connection until the answer
    is whole, so a student sees nothing meanwhile. This row lets them read the
    steps as they land. Best effort: a lost update costs a moment of progress,
    never the answer. The command and attempt that wrote the steps go with
    them, so a reader asking about one command never sees another's.
    """
    target = table or db_table.table()
    update_item = getattr(target, "update_item", None)
    if not callable(update_item):
        return False
    try:
        update_item(
            Key=generation_progress_key(conversation_id),
            UpdateExpression=(
                "SET steps=:steps, owner_id=:owner, entity_type=:entity, "
                "updated_at=:now, expires_at=:expires, command_id=:command, "
                "attempt=:attempt"
            ),
            ExpressionAttributeValues={
                ":steps": steps,
                ":owner": owner_id,
                ":entity": "conversation_generation_progress",
                ":now": now_iso,
                ":expires": expires_at,
                ":command": command_id,
                ":attempt": attempt,
            },
        )
    except Exception:
        return False
    return True


def read_generation_progress(
    conversation_id: str,
    *,
    owner_id: str,
    command_id: str | None = None,
    attempt: int | None = None,
    table: object | None = None,
) -> tuple[list[str], str]:
    """Return the steps published so far, only to the student who asked.

    Given a command and attempt, only steps that attempt wrote are returned.
    """
    target = table or db_table.table()
    try:
        item = attachment_repo._optional_mapping(
            attachment_repo._get_item(
                target, Key=generation_progress_key(conversation_id), ConsistentRead=True
            ).get("Item")
        )
    except Exception:
        return [], ""
    if item is None or item.get("owner_id") != owner_id:
        return [], ""
    if command_id is not None and (
        item.get("command_id") != command_id
        or _optional_positive_int(item.get("attempt")) != attempt
    ):
        return [], ""
    steps = item.get("steps")
    if not isinstance(steps, list):
        return [], ""
    updated_at = item.get("updated_at")
    return (
        [step for step in steps if isinstance(step, str)],
        updated_at if isinstance(updated_at, str) else "",
    )


# A command in one of these states may still be claimed, answered or retried;
# account deletion cancels it (`cancel_stale_message_command`). Moved from
# `attachment_repo` (#219).
CONVERSATION_ACTIVE_COMMAND_STATES = frozenset(
    {"claimed", "message_committed", "ai_running", "failed"}
)


def cancel_stale_message_command(
    command: dict[str, object],
    *,
    owner_id: str,
    deletion_generation: int,
    now_iso: str,
    table: object | None = None,
) -> dict[str, object]:
    """Invalidate one old-generation command and erase all replay/lease content."""
    if command.get("owner_id") != owner_id and command.get("student_id") != owner_id:
        raise attachment_repo.AttachmentRepositoryConflict("conditional_conflict")
    remove_fields = tuple(sorted(attachment_repo.CONVERSATION_PRIVATE_FIELDS))
    target = table or db_table.table()
    hook = getattr(target, "cancel_stale_message_command", None)
    if callable(hook):
        hook(
            command=command,
            owner_id=owner_id,
            deletion_generation=deletion_generation,
            remove_fields=remove_fields,
            now_iso=now_iso,
        )
    else:
        attachment_repo.scrub_conversation_private_row(
            command,
            owner_id=owner_id,
            generation=deletion_generation,
            now_iso=now_iso,
            table=target,
        )
    return {"status": "canceled", "command_id": command.get("command_id")}


def get_message_command(
    conversation_id: str,
    idempotency_key: str,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    response = attachment_repo._get_item(table or db_table.table(),
        Key=message_command_key(conversation_id, idempotency_key), ConsistentRead=True
    )
    return attachment_repo._optional_mapping(response.get("Item"))


def classify_message_command(
    command: dict[str, object] | None,
    *,
    owner_id: str,
    fingerprint: str,
    now_epoch: int,
) -> MessageCommandResult:
    """Validate identity and project one persisted command into a named state."""
    if not isinstance(command, dict):
        return MessageCommandResult(MessageCommandDisposition.MISSING)
    if command.get("owner_id") != owner_id:
        return MessageCommandResult(MessageCommandDisposition.MISSING)
    if command.get("fingerprint") != fingerprint:
        return MessageCommandResult(
            MessageCommandDisposition.IDEMPOTENCY_CONFLICT, command=dict(command)
        )
    if (
        command.get("entity_type") != "message_command"
        or command.get("schema_version") != "message-command.v2"
    ):
        return MessageCommandResult(
            MessageCommandDisposition.RETRYABLE, command=dict(command)
        )

    status = command.get("status")
    if not isinstance(status, str):
        return MessageCommandResult(
            MessageCommandDisposition.RETRYABLE, command=dict(command)
        )
    persisted = dict(command)
    counter_value = _optional_positive_int(persisted.get("counter_value"))
    if status == "claimed":
        expires_at = _optional_positive_int(persisted.get("expires_at"))
        disposition = (
            MessageCommandDisposition.EXPIRED
            if expires_at is not None and expires_at <= now_epoch
            else MessageCommandDisposition.CLAIMED
        )
    elif status == "message_committed":
        disposition = MessageCommandDisposition.RESUME
    elif status == "ai_running":
        lease_expiry = _optional_positive_int(persisted.get("expiresAt"))
        disposition = (
            MessageCommandDisposition.RESUME
            if lease_expiry is not None and lease_expiry <= now_epoch
            else MessageCommandDisposition.LEASE_HELD
        )
    elif status == "completed":
        disposition = (
            MessageCommandDisposition.COMPLETED
            if isinstance(persisted.get("result_json"), str)
            and bool(persisted["result_json"])
            else MessageCommandDisposition.RETRYABLE
        )
    elif status == "rejected":
        disposition = MessageCommandDisposition.REJECTED
    elif status == "terminal_failed":
        disposition = MessageCommandDisposition.TERMINAL
    elif status == "failed":
        disposition = (
            MessageCommandDisposition.RESUME
            if failed_command_can_retry(persisted)
            else MessageCommandDisposition.TERMINAL
        )
    elif status == "expired":
        disposition = MessageCommandDisposition.EXPIRED
    else:
        disposition = MessageCommandDisposition.RETRYABLE
    return MessageCommandResult(
        disposition,
        command=persisted,
        counter_value=counter_value,
        error_code=(
            str(persisted["error_code"])
            if isinstance(persisted.get("error_code"), str)
            else None
        ),
        attempt=_optional_positive_int(persisted.get("attempt")) or 0,
    )


def failed_command_can_retry(
    command: Mapping[str, object], max_attempts: int = MESSAGE_AI_MAX_ATTEMPTS
) -> bool:
    """A failed generation is tried again only if nothing was paid for and
    attempts remain."""
    return (
        command.get("failure_retryable") is True
        and (_optional_positive_int(command.get("attempt")) or 0) < max_attempts
    )


def read_message_command_result(
    conversation_id: str,
    idempotency_key: str,
    *,
    owner_id: str,
    fingerprint: str,
    now_epoch: int = 0,
    table: object | None = None,
) -> MessageCommandResult:
    try:
        command = get_message_command(conversation_id, idempotency_key, table=table)
    except Exception:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=now_epoch,
    )


def _optional_positive_int(value: object) -> int | None:
    # Reads a stored counter, and DynamoDB returns stored numbers as Decimal.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
        return parsed if parsed >= 0 else None
    return None


def build_message_command_claim_transaction(
    *,
    command: dict[str, object],
    owner_id: str,
    quota_period: str,
    expected_counter: int,
    limit: int,
    expires_at: int,
    account_fence_generation: int = 1,
) -> list[attachment_repo.TransactionOperation]:
    command_id = str(command["command_id"])
    expected_exists = expected_counter > 0
    # The daily limit is compared in the caller, which reads the counter before
    # building this. DynamoDB cannot compare two placeholders: the left operand
    # of a comparator must be a document path, so asking it to check the limit
    # here made every claim fail validation. What this must enforce is that no
    # concurrent claim moved the counter, which is the compare-and-set below.
    # A 0 the caller read is either no row or a row holding 0: compensating a
    # rejected first message leaves the latter (1 -> 0), and conditioning on a
    # missing attribute alone refused every claim for the rest of that day
    # (#102). The question counter takes both the same way.
    counter_condition = (
        "#count=:expected"
        if expected_exists
        else "attribute_not_exists(#count) OR #count=:expected"
    )
    values: dict[str, object] = {
        ":next": expected_counter + 1,
        ":expires": expires_at,
        ":expected": expected_counter,
    }
    return [
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_PUT,
            {
                "Put": {
                    "Item": {
                        **message_command_key(
                            str(command["conversation_id"]), str(command["idempotency_key"])
                        ),
                        **command,
                        "owner_id": owner_id,
                        "student_id": owner_id,
                        "account_fence_generation": account_fence_generation,
                        "counter_value": expected_counter + 1,
                        "quota_period": quota_period,
                        "expires_at": expires_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.CHAT_QUOTA_OPERATION_PUT,
            {
                "Put": {
                    "Item": {
                        **chat_quota_operation_key(owner_id, command_id),
                        "entity_type": "chat_quota_operation",
                        "command_id": command_id,
                        "owner_id": owner_id,
                        "quota_period": quota_period,
                        "counter_value": expected_counter + 1,
                        "created_at": command["created_at"],
                        "expires_at": expires_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.CHAT_QUOTA_UPDATE,
            {
                "Update": {
                    "Key": chat_quota_key(owner_id, quota_period),
                    "UpdateExpression": "SET #count=:next, #ttl=if_not_exists(#ttl,:expires)",
                    "ConditionExpression": counter_condition,
                    "ExpressionAttributeNames": {"#count": "count", "#ttl": "expires_at"},
                    "ExpressionAttributeValues": {
                        **values,
                    },
                }
            },
        ),
    ]


def _message_usage_event_item(
    *, command: dict[str, object], owner_id: str, now_iso: str
) -> dict[str, object]:
    action = attachment_repo._required_text(command.get("usage_action"))
    quota_period = attachment_repo._required_text(command.get("quota_period"))
    idempotency_key = attachment_repo._required_text(command.get("usage_idempotency_key"))
    counter_value = attachment_repo._required_integer(command.get("counter_value"), minimum=1)
    resource_id = attachment_repo._required_text(command.get("usage_resource_id"))
    return {
        "PK": f"USAGE_LEDGER#{owner_id}",
        "SK": f"EVENT#{action}#{quota_period}#{idempotency_key}",
        "entity_type": "usage_ledger_event",
        "schema_version": "usage-ledger.v1",
        "event_id": attachment_repo._required_text(command.get("usage_event_id")),
        "actor_id": owner_id,
        "actor_role": "student",
        "student_id": owner_id,
        "action": action,
        "quantity": 1,
        "quota_period": quota_period,
        "counter_key": f"USAGE#{owner_id}/CHAT#{quota_period}",
        "counter_value_after": counter_value,
        "idempotency_key": idempotency_key,
        "request_correlation_id": resource_id,
        "privacy": {
            "raw_content_stored": False,
            "raw_learning_content_stored": False,
            "private_artifact_keys_stored": False,
            "provider_payloads_stored": False,
            "auth_tokens_stored": False,
            "verification_codes_stored": False,
        },
        "metadata": {
            "usage_type": "daily_chat_message",
            "summary_group": "chat",
            "quota_enforced": True,
            "support_visible": True,
            "conversation_id": attachment_repo._required_text(command.get("conversation_id")),
            "request_id": resource_id,
            "status": "sent",
            "write_order": "message_effect_transaction",
        },
        "created_at": attachment_repo._required_text(command.get("created_at")),
        "updated_at": now_iso,
        "expires_at": attachment_repo._required_integer(command.get("expires_at"), minimum=1),
    }


def message_committed_operations(
    command: dict[str, object], *, owner_id: str, now_iso: str
) -> list[attachment_repo.TransactionOperation]:
    """What the student's message commit writes of the question, after the message itself.

    The chat usage event the claim counted, and the command's step from
    `claimed` to `message_committed`. They join the message's own transaction
    (`attachment_service.bind_message_attachments`, as its
    `command_operations`), last, so the command is committed exactly when the
    message and its attachments are.
    """
    return [
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.USAGE_EVENT_PUT,
            {
                "Put": {
                    "Item": _message_usage_event_item(
                        command=command, owner_id=owner_id, now_iso=now_iso
                    ),
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
            {
                "Update": {
                    "Key": message_command_key(
                        attachment_repo._required_text(command.get("conversation_id")),
                        attachment_repo._required_text(command.get("idempotency_key")),
                    ),
                    "UpdateExpression": "SET #status=:committed, message_committed_at=:now",
                    "ConditionExpression": (
                        "owner_id=:owner AND fingerprint=:fingerprint AND #status=:claimed"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":fingerprint": command["fingerprint"],
                        ":claimed": "claimed",
                        ":committed": "message_committed",
                        ":now": now_iso,
                    },
                }
            },
        ),
    ]


def claim_message_command_and_quota(
    *,
    command: dict[str, object],
    owner_id: str,
    quota_period: str,
    limit: int,
    expires_at: int,
    account_fence_generation: int = 1,
    table: object | None = None,
) -> MessageCommandResult:
    """Atomically create a message command and charge its daily quota once."""
    target = table or db_table.table()
    fingerprint = str(command["fingerprint"])
    now_epoch = max(0, expires_at - 172800)
    existing = read_message_command_result(
        str(command["conversation_id"]),
        str(command["idempotency_key"]),
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=now_epoch,
        table=target,
    )
    if existing.disposition is not MessageCommandDisposition.MISSING:
        return existing

    expected = 0
    for _ in range(3):
        try:
            raw_counter = attachment_repo._get_item(target,
                Key=chat_quota_key(owner_id, quota_period), ConsistentRead=True
            ).get("Item")
            counter = attachment_repo._optional_mapping(raw_counter) or {}
        except Exception:
            raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
        expected = attachment_repo._required_integer(counter.get("count", 0))
        if expected >= limit:
            raced = read_message_command_result(
                str(command["conversation_id"]),
                str(command["idempotency_key"]),
                owner_id=owner_id,
                fingerprint=fingerprint,
                now_epoch=now_epoch,
                table=target,
            )
            if raced.disposition is not MessageCommandDisposition.MISSING:
                if raced.disposition is MessageCommandDisposition.CLAIMED:
                    return MessageCommandResult(
                        MessageCommandDisposition.RESUME,
                        command=raced.command,
                        counter_value=raced.counter_value,
                        attempt=raced.attempt,
                    )
                return raced
            return MessageCommandResult(
                MessageCommandDisposition.QUOTA_EXCEEDED,
                counter_value=expected,
            )
        operations = build_message_command_claim_transaction(
            command=command,
            owner_id=owner_id,
            quota_period=quota_period,
            expected_counter=expected,
            limit=limit,
            expires_at=expires_at,
            account_fence_generation=account_fence_generation,
        )
        try:
            attachment_repo.transact(
                operations,
                table=target,
                owner=owner_id,
                generation=account_fence_generation,
            )
        except attachment_repo.AttachmentTransactionError as exc:
            if exc.outcome is attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY:
                return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
            raced = read_message_command_result(
                str(command["conversation_id"]),
                str(command["idempotency_key"]),
                owner_id=owner_id,
                fingerprint=fingerprint,
                now_epoch=now_epoch,
                table=target,
            )
            if raced.disposition is not MessageCommandDisposition.MISSING:
                if raced.disposition is MessageCommandDisposition.CLAIMED:
                    return MessageCommandResult(
                        MessageCommandDisposition.RESUME,
                        command=raced.command,
                        counter_value=raced.counter_value,
                        attempt=raced.attempt,
                    )
                return raced
            continue
        persisted = {
            **command,
            "owner_id": owner_id,
            "student_id": owner_id,
            "account_fence_generation": account_fence_generation,
            "counter_value": expected + 1,
            "quota_period": quota_period,
            "expires_at": expires_at,
        }
        return MessageCommandResult(
            MessageCommandDisposition.CLAIMED,
            command=persisted,
            counter_value=expected + 1,
        )
    return MessageCommandResult(
        MessageCommandDisposition.RETRYABLE,
        counter_value=expected,
    )


def kept_answer_attempt(command: Mapping[str, object]) -> int | None:
    """The attempt that called the model and stored its answer on the command.

    None unless the stored answer is the called attempt's own, which is what
    recovery finishes from (`_answering._stored_provider_result`). Storing
    it needs no model call, so it is finished even when that attempt was the
    last (E28).
    """
    attempt = _optional_positive_int(command.get("provider_result_attempt"))
    if (
        attempt is None
        or attempt != _optional_positive_int(command.get("provider_invoked_attempt"))
        or not isinstance(command.get("provider_result_json"), str)
    ):
        return None
    return attempt


def claim_message_ai_lease(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    now_epoch: int,
    expires_at: int,
    max_attempts: int = MESSAGE_AI_MAX_ATTEMPTS,
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> MessageCommandResult:
    target = table or db_table.table()
    try:
        command = get_message_command(conversation_id, idempotency_key, table=target) or {}
    except Exception:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    persisted_attempt = _optional_positive_int(command.get("attempt")) or 0
    # A last attempt that died after storing its answer may be claimed again,
    # only to store it: that is not another try, so the count stays. The
    # condition below carries the same test.
    finishing = (
        persisted_attempt == max_attempts
        and kept_answer_attempt(command) == max_attempts
    )
    attempt = persisted_attempt if finishing else persisted_attempt + 1
    generation = account_fence_generation or command.get("account_fence_generation")
    if type(generation) is not int or generation <= 0:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    command_status = command.get("status")
    can_claim = (
        command_status == "message_committed"
        or (
            command_status == "ai_running"
            and (_optional_positive_int(command.get("expiresAt")) or 0) <= now_epoch
            and attempt <= max_attempts
        )
        or (command_status == "failed" and failed_command_can_retry(command, max_attempts))
    )
    # The claim acts on what it read about an earlier call. A lost attempt may
    # still mark a call after that read, until its own lease clock runs out, so
    # the mark is part of the condition: a claim over a changed mark fails.
    invoked_mark = _optional_positive_int(command.get("provider_invoked_attempt"))
    mark_condition = (
        "attribute_not_exists(provider_invoked_attempt)"
        if invoked_mark is None
        else "provider_invoked_attempt=:mark"
    )
    mark_values: dict[str, object] = {} if invoked_mark is None else {":mark": invoked_mark}
    if not can_claim or attempt > max_attempts:
        if command_status == "completed":
            disposition = MessageCommandDisposition.COMPLETED
        elif command_status == "rejected":
            disposition = MessageCommandDisposition.REJECTED
        elif command_status == "failed" or persisted_attempt >= max_attempts:
            disposition = MessageCommandDisposition.TERMINAL
        elif command_status == "ai_running":
            disposition = MessageCommandDisposition.LEASE_HELD
        else:
            disposition = MessageCommandDisposition.RETRYABLE
        return MessageCommandResult(
            disposition,
            command=dict(command),
            counter_value=_optional_positive_int(command.get("counter_value")),
            error_code=(
                str(command["error_code"])
                if isinstance(command.get("error_code"), str)
                else None
            ),
            attempt=persisted_attempt,
        )
    try:
        attachment_repo.transact(
            [
                attachment_repo.TransactionOperation(
                    attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
                    {
                        "Update": {
                            "Key": message_command_key(conversation_id, idempotency_key),
                            "UpdateExpression": (
                                "SET #status=:running, leaseOwner=:lease_owner, claimedAt=:claimed, "
                                "expiresAt=:expires, attempt=:attempt "
                                f"REMOVE {', '.join(MESSAGE_FAILURE_FIELDS)}"
                            ),
                            "ConditionExpression": (
                                "owner_id=:owner AND account_fence_generation=:generation AND "
                                "(#status=:committed OR (#status=:running AND "
                                "expiresAt<=:now AND attempt<:max_attempts) OR "
                                "(#status=:running AND expiresAt<=:now AND "
                                "attempt=:max_attempts AND "
                                "provider_result_attempt=:max_attempts AND "
                                "attribute_exists(provider_result_json)) OR "
                                "(#status=:failed AND failure_retryable=:retryable AND "
                                "attempt<:max_attempts)) AND "
                                + mark_condition
                            ),
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": {
                                ":owner": owner_id,
                                ":generation": generation,
                                ":committed": "message_committed",
                                ":running": "ai_running",
                                ":failed": "failed",
                                ":retryable": True,
                                ":lease_owner": lease_owner,
                                ":claimed": now_epoch,
                                ":expires": expires_at,
                                ":now": now_epoch,
                                ":attempt": attempt,
                                ":max_attempts": max_attempts,
                                **mark_values,
                            },
                        }
                    },
                ),
            ],
            table=target,
            owner=owner_id,
            generation=generation,
        )
    except attachment_repo.AttachmentTransactionError as exc:
        if exc.outcome is attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT:
            try:
                reread = get_message_command(
                    conversation_id, idempotency_key, table=target
                )
            except Exception:
                return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
            if isinstance(reread, dict) and reread.get("owner_id") == owner_id:
                current_fingerprint = reread.get("fingerprint")
                if isinstance(current_fingerprint, str):
                    return classify_message_command(
                        reread,
                        owner_id=owner_id,
                        fingerprint=current_fingerprint,
                        now_epoch=now_epoch,
                    )
            return MessageCommandResult(MessageCommandDisposition.MISSING)
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    claimed = {
        **{
            key: value
            for key, value in command.items()
            if key not in MESSAGE_FAILURE_FIELDS
        },
        "status": "ai_running",
        "leaseOwner": lease_owner,
        "claimedAt": now_epoch,
        "expiresAt": expires_at,
        "attempt": attempt,
    }
    return MessageCommandResult(
        MessageCommandDisposition.CLAIMED,
        command=claimed,
        counter_value=_optional_positive_int(command.get("counter_value")),
        attempt=attempt,
        previous_status=str(command_status),
    )


def complete_message_command(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    assistant_message_put: dict[str, object],
    result_json: str,
    completed_at: str,
    lease_attempt: int = 1,
    completed_epoch: int = 0,
    account_fence_generation: int = 1,
    knowledge_gap_updates: Sequence[dict[str, object]] = (),
    asked_knowledge_put: dict[str, object] | None = None,
    table: object | None = None,
) -> MessageCommandResult:
    """Store the answer and settle the command, in one transaction.

    `knowledge_gap_updates` (#142) and `asked_knowledge_put` (#143) ride in the
    same transaction, so they count once, and only for an answer that was
    stored. Two answers counting the same gap at the same moment cancel each
    other (`TransactionConflict`); a count is not worth an answer, so a
    transaction that fails with them is tried once more without them. The
    record of what the question asked about is the student's own and collides
    with nothing, so it is kept on that retry.
    """
    if (
        isinstance(lease_attempt, bool)
        or not isinstance(lease_attempt, int)
        or lease_attempt <= 0
        or isinstance(completed_epoch, bool)
        or not isinstance(completed_epoch, int)
        or completed_epoch < 0
    ):
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    operations = [
        # The answer's own put, as `learning_session.append` made it (#227).
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.ASSISTANT_MESSAGE_PUT,
            assistant_message_put,
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
            {
                "Update": {
                    "Key": message_command_key(conversation_id, idempotency_key),
                    "UpdateExpression": (
                        "SET #status=:completed, result_json=:result, completed_at=:completed_at "
                        "REMOVE leaseOwner, claimedAt, expiresAt, "
                        + ", ".join(MESSAGE_ATTEMPT_TRACE_FIELDS)
                    ),
                    "ConditionExpression": (
                        "owner_id=:owner AND account_fence_generation=:generation AND #status=:running AND "
                        "leaseOwner=:lease_owner AND attempt=:lease_attempt AND "
                        "expiresAt>:completed_epoch"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":generation": account_fence_generation,
                        ":running": "ai_running",
                        ":completed": "completed",
                        ":lease_owner": lease_owner,
                        ":lease_attempt": lease_attempt,
                        ":completed_epoch": completed_epoch,
                        ":result": result_json,
                        ":completed_at": completed_at,
                    },
                }
            },
        ),
        *(
            attachment_repo.TransactionOperation(attachment_repo.TransactionOperationKind.KNOWLEDGE_GAP_UPDATE, dict(update))
            for update in knowledge_gap_updates
        ),
        *(
            [attachment_repo.TransactionOperation(attachment_repo.TransactionOperationKind.ASKED_KNOWLEDGE_PUT, dict(asked_knowledge_put))]
            if asked_knowledge_put is not None
            else []
        ),
    ]
    try:
        attachment_repo.transact(
            operations, table=table, owner=owner_id, generation=account_fence_generation
        )
    except attachment_repo.AttachmentTransactionError:
        try:
            command = get_message_command(
                conversation_id, idempotency_key, table=table
            )
        except Exception:
            return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
        if (
            isinstance(command, dict)
            and command.get("owner_id") == owner_id
            and command.get("status") == "completed"
            and isinstance(command.get("result_json"), str)
            and command["result_json"]
        ):
            return MessageCommandResult(
                MessageCommandDisposition.COMPLETED,
                command=dict(command),
                counter_value=_optional_positive_int(command.get("counter_value")),
            )
        if knowledge_gap_updates:
            return complete_message_command(
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                owner_id=owner_id,
                lease_owner=lease_owner,
                assistant_message_put=assistant_message_put,
                result_json=result_json,
                completed_at=completed_at,
                lease_attempt=lease_attempt,
                completed_epoch=completed_epoch,
                account_fence_generation=account_fence_generation,
                asked_knowledge_put=asked_knowledge_put,
                table=table,
            )
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    return MessageCommandResult(MessageCommandDisposition.COMPLETED)


def record_message_generation_context(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    context: dict[str, object],
    table: object | None = None,
) -> dict[str, object]:
    """Store what the answer is generated from on a command that lacks it.

    Commands claimed before the context moved onto the command are resumed
    with the context of the request that resumes them. The first stored context
    wins, so two resuming requests agree on one language. Returns the stored one.
    """
    try:
        response = attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression="SET generation_context=if_not_exists(generation_context, :context)",
            ConditionExpression=(
                "owner_id=:owner AND #status IN (:committed, :running, :failed)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":context": context,
                ":committed": "message_committed",
                ":running": "ai_running",
                ":failed": "failed",
            },
            ReturnValues="ALL_NEW",
        )
    except db_table.WriteRefused:
        raise attachment_repo.AttachmentRepositoryConflict("conditional_conflict") from None
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    stored = attachment_repo._optional_mapping(response.get("Attributes"))
    stored_context = attachment_repo._optional_mapping((stored or {}).get("generation_context"))
    if stored_context is None:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")
    return dict(stored_context)


def reopen_failed_message_command(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    attempt: int,
    now_iso: str,
    table: object | None = None,
) -> bool:
    """Put a failed command the student sends again back to waiting.

    Only while that failure is retryable and still the latest attempt: a
    request that read an older attempt changes nothing. Waiting is what the
    student's chat reads while the answer is on its way, and what the sweep
    takes up if the worker's invoke is lost.
    """
    try:
        attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:committed, message_committed_at=:now "
                f"REMOVE {', '.join(MESSAGE_FAILURE_FIELDS)}"
            ),
            ConditionExpression=(
                "owner_id=:owner AND #status=:failed AND failure_retryable=:retryable "
                "AND attempt=:attempt AND attempt<:max_attempts"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":failed": "failed",
                ":committed": "message_committed",
                ":retryable": True,
                ":attempt": attempt,
                ":max_attempts": MESSAGE_AI_MAX_ATTEMPTS,
                ":now": now_iso,
            },
        )
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def fail_message_command(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    lease_attempt: int,
    failure_category: str,
    retryable: bool,
    now_iso: str,
    table: object | None = None,
) -> bool:
    """End the leased attempt as failed, instead of leaving it to its lease.

    `retryable` says whether the same command may be generated again: only when
    no provider result was paid for. Returns False when the lease was no longer
    this attempt's, which leaves the command as the newer holder left it.
    """
    try:
        attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:failed, failure_category=:category, "
                "failure_retryable=:retryable, failed_at=:now "
                "REMOVE leaseOwner, claimedAt, expiresAt, "
                + ", ".join(MESSAGE_ATTEMPT_TRACE_FIELDS)
            ),
            ConditionExpression=(
                "owner_id=:owner AND #status=:running AND leaseOwner=:lease_owner "
                "AND attempt=:attempt"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":failed": "failed",
                ":lease_owner": lease_owner,
                ":attempt": lease_attempt,
                ":category": failure_category,
                ":retryable": retryable,
                ":now": now_iso,
            },
        )
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def _leased_command_update(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    lease_attempt: int,
    now_epoch: int,
    update_expression: str,
    values: dict[str, object],
    table: object | None,
) -> bool:
    """One write the attempt holding an unexpired lease may make; False if it does not."""
    try:
        attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=update_expression,
            ConditionExpression=(
                "owner_id=:owner AND #status=:running AND leaseOwner=:lease_owner "
                "AND attempt=:attempt AND expiresAt>:now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":lease_owner": lease_owner,
                ":attempt": lease_attempt,
                ":now": now_epoch,
                **values,
            },
        )
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def record_provider_invocation(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    lease_attempt: int,
    now_epoch: int,
    table: object | None = None,
) -> bool:
    """Mark that this attempt is about to call the model, before it does.

    Once the mark is there, an attempt whose lease runs out without a stored
    result may have been paid for, so it is never called again (ticket 08,
    constraint 2). Returns False when the lease is no longer this attempt's,
    and then the model must not be called.
    """
    return _leased_command_update(
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        owner_id=owner_id,
        lease_owner=lease_owner,
        lease_attempt=lease_attempt,
        now_epoch=now_epoch,
        update_expression="SET provider_invoked_attempt=:attempt",
        values={},
        table=table,
    )


def record_provider_result(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    lease_attempt: int,
    now_epoch: int,
    result_json: str,
    table: object | None = None,
) -> bool:
    """Keep the answer the model gave this attempt until it is stored for good.

    A later attempt that finds it finishes storing it instead of calling the
    model again. Completion removes it.
    """
    return _leased_command_update(
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        owner_id=owner_id,
        lease_owner=lease_owner,
        lease_attempt=lease_attempt,
        now_epoch=now_epoch,
        update_expression=(
            "SET provider_result_json=:result, provider_result_attempt=:attempt"
        ),
        values={":result": result_json},
        table=table,
    )


# Pages one sweep may read. The filtered scan reads the whole table, which is
# a few pages today; a run that reaches this says so, and the table has then
# outgrown a scan (a sparse index on waiting commands would replace it).
GENERATION_SWEEP_MAX_PAGES = 50


# Failures that may leave an allowance reservation nothing else settles: a
# model call whose answer was lost, and a reservation kept at admission when no
# time was left to call (E10). The sweep settles them (E24).
UNSETTLED_RESERVATION_FAILURES = ("needs_reconciliation", "deadline_exceeded")


# When each ended state was reached; a write to settle one is conditioned on it
# still being the end the sweep read. `terminal_failed` is a command whose last
# attempt died, or whose lease nobody took up (E27).
SETTLEMENT_ENDED_AT = {"failed": "failed_at", "terminal_failed": "terminal_at"}


def scan_generation_sweep_commands(
    *, table: object | None = None, max_pages: int = GENERATION_SWEEP_MAX_PAGES
) -> tuple[list[dict[str, object]], bool]:
    """Every command the sweep may act on, and whether the scan finished.

    Those still waiting for an answer, and failed ones whose reservation may
    still need settling. Eventually consistent: a command written in the last
    moment is picked up by the next run, and whatever acts on one does so
    conditionally anyway.
    """
    target = table or db_table.table()
    if not isinstance(target, attachment_repo._ScanTable):
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")
    request: dict[str, object] = {
        "FilterExpression": (
            "entity_type=:entity AND (#status IN (:committed, :running) OR "
            "(((#status=:failed AND failure_category IN (:needs_reconciliation, "
            ":deadline_exceeded)) OR #status=:terminal) AND "
            "attribute_not_exists(allowance_settled_at)))"
        ),
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":entity": "message_command",
            ":committed": "message_committed",
            ":running": "ai_running",
            ":failed": "failed",
            ":terminal": "terminal_failed",
            **{f":{category}": category for category in UNSETTLED_RESERVATION_FAILURES},
        },
    }
    commands: list[dict[str, object]] = []
    try:
        for page in islice(db_table.pages("scan", table=target, **request), max_pages):
            commands.extend(page.items)
            if page.last_key is None:
                return commands, True
    except db_table.TableUnavailable as exc:
        if exc.code.startswith("malformed"):
            raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
        raise
    return commands, False


def _unsettled_end_update(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    status: str,
    ended_at: str,
    update_expression: str,
    values: dict[str, object],
    table: object | None,
) -> bool:
    """One write to an ended command still as the sweep read it and not yet settled."""
    try:
        attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=update_expression,
            ConditionExpression=(
                f"owner_id=:owner AND #status=:status AND {SETTLEMENT_ENDED_AT[status]}"
                "=:ended_at AND attribute_not_exists(allowance_settled_at)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":status": status,
                ":ended_at": ended_at,
                **values,
            },
        )
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def close_failure_for_settlement(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    failed_at: str,
    table: object | None = None,
) -> bool:
    """Stop the same command being tried again before its reservation is released.

    A retry would reuse a reservation that is about to be gone. False when the
    failure is no longer the one read (the student sent it again) or is settled.
    """
    return _unsettled_end_update(
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        owner_id=owner_id,
        status="failed",
        ended_at=failed_at,
        update_expression="SET failure_retryable=:not_retryable",
        values={":not_retryable": False},
        table=table,
    )


def mark_allowance_settled(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    status: str,
    ended_at: str,
    now_iso: str,
    table: object | None = None,
) -> bool:
    """Record that the command's reservation is settled, so it is settled once.

    `status` is `failed` or `terminal_failed`, and `ended_at` its `failed_at`
    or `terminal_at` as the sweep read it.
    """
    return _unsettled_end_update(
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        owner_id=owner_id,
        status=status,
        ended_at=ended_at,
        update_expression="SET allowance_settled_at=:now",
        values={":now": now_iso},
        table=table,
    )


def close_stale_lease(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    expires_at: int,
    now_epoch: int,
    now_iso: str,
    table: object | None = None,
) -> bool:
    """End a command whose lease ran out and that nobody took up (E27).

    `terminal_failed`, as if its attempts were used up, so no retry reuses the
    reservation about to be released and `/generation` reports an end. Only
    while the lease is the expired one the sweep read: a student who sent it
    again since holds a new one, and False leaves the command to them.
    """
    try:
        attachment_repo._update_item(
            table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:terminal, terminal_at=:now_iso "
                "REMOVE leaseOwner, claimedAt, expiresAt"
            ),
            ConditionExpression=(
                "owner_id=:owner AND #status=:running AND leaseOwner=:lease_owner "
                "AND expiresAt=:expires AND expiresAt<=:now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":terminal": "terminal_failed",
                ":lease_owner": lease_owner,
                ":expires": expires_at,
                ":now": now_epoch,
                ":now_iso": now_iso,
            },
        )
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable:
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def renew_message_ai_lease(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    now_epoch: int,
    expires_at: int,
    account_fence_generation: int = 1,
    table: object | None = None,
) -> bool:
    try:
        attachment_repo.transact(
            [
                attachment_repo.TransactionOperation(
                    attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
                    {
                        "Update": {
                            "Key": message_command_key(conversation_id, idempotency_key),
                            "UpdateExpression": "SET claimedAt=:now, expiresAt=:expires",
                            "ConditionExpression": (
                                "owner_id=:owner AND account_fence_generation=:generation AND "
                                "#status=:running AND leaseOwner=:lease_owner AND expiresAt>:now"
                            ),
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": {
                                ":owner": owner_id,
                                ":generation": account_fence_generation,
                                ":running": "ai_running",
                                ":lease_owner": lease_owner,
                                ":now": now_epoch,
                                ":expires": expires_at,
                            },
                        }
                    },
                ),
            ],
            table=table,
            owner=owner_id,
            generation=account_fence_generation,
        )
    except attachment_repo.AttachmentTransactionError as exc:
        if exc.outcome is attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT:
            return False
        raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None
    return True


def reject_message_command_and_compensate(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    fingerprint: str,
    error_code: str,
    now_iso: str,
    table: object | None = None,
) -> MessageCommandResult:
    """Terminally reject a pre-bind command and reverse its one quota claim."""
    target = table or db_table.table()
    try:
        command = get_message_command(conversation_id, idempotency_key, table=target)
    except Exception:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    current = classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=0,
    )
    if current.disposition is not MessageCommandDisposition.CLAIMED:
        return current
    assert current.command is not None
    command_id = attachment_repo._required_text(current.command.get("command_id"))
    quota_period = attachment_repo._required_text(current.command.get("quota_period"))
    counter_value = attachment_repo._required_integer(
        current.command.get("counter_value"), minimum=1
    )
    operations = (
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_REJECT,
            {
                "Update": {
                    "Key": message_command_key(conversation_id, idempotency_key),
                    "UpdateExpression": (
                        "SET #status=:rejected, error_code=:error, rejected_at=:now"
                    ),
                    "ConditionExpression": (
                        "owner_id=:owner AND fingerprint=:fingerprint AND #status=:claimed"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":fingerprint": fingerprint,
                        ":claimed": "claimed",
                        ":rejected": "rejected",
                        ":error": error_code,
                        ":now": now_iso,
                    },
                }
            },
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.CHAT_QUOTA_OPERATION_DELETE,
            {
                "Delete": {
                    "Key": chat_quota_operation_key(owner_id, command_id),
                    "ConditionExpression": "command_id=:command",
                    "ExpressionAttributeValues": {":command": command_id},
                }
            },
        ),
        attachment_repo.TransactionOperation(
            attachment_repo.TransactionOperationKind.CHAT_QUOTA_COMPENSATE,
            {
                "Update": {
                    "Key": chat_quota_key(owner_id, quota_period),
                    "UpdateExpression": "SET #count=#count-:one",
                    "ConditionExpression": "#count=:expected AND #count>:zero",
                    "ExpressionAttributeNames": {"#count": "count"},
                    "ExpressionAttributeValues": {
                        ":one": 1,
                        ":zero": 0,
                        ":expected": counter_value,
                    },
                }
            },
        ),
    )
    try:
        attachment_repo.transact(list(operations), table=target)
    except attachment_repo.AttachmentTransactionError:
        try:
            reread = get_message_command(
                conversation_id, idempotency_key, table=target
            )
        except Exception:
            return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
        reconciled = classify_message_command(
            reread,
            owner_id=owner_id,
            fingerprint=fingerprint,
            now_epoch=0,
        )
        if reconciled.disposition is MessageCommandDisposition.REJECTED:
            return reconciled
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    rejected = {
        **current.command,
        "status": "rejected",
        "error_code": error_code,
        "rejected_at": now_iso,
    }
    return MessageCommandResult(
        MessageCommandDisposition.REJECTED,
        command=rejected,
        counter_value=counter_value,
        error_code=error_code,
        operations=operations,
    )


def mark_message_command_terminal(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    now_iso: str,
    table: object | None = None,
) -> MessageCommandResult:
    try:
        attachment_repo._update_item(table or db_table.table(),
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:terminal, terminal_at=:now REMOVE leaseOwner, claimedAt, expiresAt"
            ),
            # A command holding its answer is finished, never ended here (E28).
            ConditionExpression=(
                "owner_id=:owner AND #status=:running AND attempt>=:max AND "
                "attribute_not_exists(provider_result_json)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":terminal": "terminal_failed",
                ":now": now_iso,
                ":max": 3,
            },
        )
    except db_table.WriteRefused:
        try:
            command = get_message_command(
                conversation_id, idempotency_key, table=table
            )
        except Exception:
            return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
        if isinstance(command, dict) and command.get("owner_id") == owner_id:
            fingerprint = command.get("fingerprint")
            if isinstance(fingerprint, str):
                return classify_message_command(
                    command,
                    owner_id=owner_id,
                    fingerprint=fingerprint,
                    now_epoch=0,
                )
        return MessageCommandResult(MessageCommandDisposition.MISSING)
    except db_table.TableUnavailable:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    # Only this write ended the command; a later reader finds it already ended.
    return MessageCommandResult(
        MessageCommandDisposition.TERMINAL, previous_status="ai_running"
    )
