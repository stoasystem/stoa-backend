"""Owner-fenced notification, assistance, device, and delivery persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import islice
from typing import Protocol, runtime_checkable
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo


NOTIFICATION_ENTITY = "notification_event"
# A teacher assistance summary seed (`ASSISTANCE_SUMMARY#<id>`, `META`). Nothing
# writes one since #518 retired `GET /teachers/questions/{id}/assistance-summary`;
# rows stored before are still deleted with the student's account.
SUMMARY_SEED_ENTITY = "teacher_assistance_summary_seed"
PREFERENCE_ENTITY = "notification_preference"
PUSH_TOKEN_ENTITY = "notification_push_token"
DELIVERY_INTENT_ENTITY = "notification_delivery_intent"
PAYMENT_EXPIRY_REMINDER_ENTITY = "payment_expiry_reminder"
GLOBAL_NONPRIVATE_CONTRACT_ID = "stoa-global-nonprivate.v1"
GLOBAL_NONPRIVATE_DELIVERY_CONTRACTS = {
    GLOBAL_NONPRIVATE_CONTRACT_ID: {
        "event_types": frozenset(
            {"moderation_case_update", "subscription_request_update"}
        ),
        "target_types": frozenset({"system_status"}),
        "metadata_keys": frozenset(),
    }
}

NOTIFICATION_PRIVATE_ROW_REGISTRY = frozenset(
    {
        NOTIFICATION_ENTITY,
        SUMMARY_SEED_ENTITY,
        PREFERENCE_ENTITY,
        PUSH_TOKEN_ENTITY,
        DELIVERY_INTENT_ENTITY,
        PAYMENT_EXPIRY_REMINDER_ENTITY,
    }
)
NOTIFICATION_WRITER_REGISTRY = frozenset(
    {
        "put_event",
        "update_event",
        "put_preferences",
        "put_push_token",
        "update_push_token",
        "register_delivery_intent",
        "claim_delivery_intent",
        "begin_delivery_effect",
        "recover_delivery_intent",
        "cancel_delivery_intent",
        "complete_delivery_intent",
        "put_payment_expiry_reminder",
        "resolve_payment_expiry_reminder",
        "mark_payment_expiry_reminder_notified",
    }
)
NOTIFICATION_PRIVATE_FIELDS = frozenset(
    {
        "recipient_id",
        "recipient_role",
        "actor_id",
        "actor_role",
        "event_type",
        "target_type",
        "target_id",
        "title",
        "summary",
        "metadata",
        "category",
        "question_id",
        "student_id",
        "subject",
        "student_context_summary",
        "question_summary",
        "ai_answer_summary",
        "weak_topics",
        "suggested_focus",
        "source_count",
        "created_by",
        "preferences",
        "role",
        "platform",
        "token_reference",
        "token_hash",
        "provider_token_reference",
        "device_id_hash",
        "event_ids",
        "payload_digest",
        "lease_owner",
        "lease_expires_at",
        "endpoint_url",
        "subscribed_channels",
        "parent_id",
        "payment_method_digest",
        "brand",
        "last4",
        "exp_month",
        "exp_year",
        "source_subscription_digest",
        "observation_version",
        "reminder_identity",
        "reminder_at",
        "resolved_at",
        "notified_at",
    }
)
NOTIFICATION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "status",
        "event_id",
        "summary_id",
        "operation_id",
        "channel",
        "created_at",
        "accepted_at",
        "updated_at",
        "deleted_at",
        "owner_deletion_generation",
    }
)
EXTERNAL_DELIVERY_RETENTION_BOUNDARY = {
    "provider_accepted_or_unknown": "outside_backend_deletion_control"
}
_EXTERNAL_RECEIPT_STATES = frozenset({"accepted", "provider_acceptance_unknown"})


type NotificationItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


def _dependency_mapping(value: object) -> NotificationItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed notification dependency response"
        )
    result: NotificationItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed notification dependency response"
            )
        result[key] = member
    return result


def _optional_item(value: object) -> NotificationItem | None:
    if value is None:
        return None
    return _dependency_mapping(value)


def _response_items(response: Mapping[str, object]) -> list[NotificationItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed notification dependency response"
        )
    return [_dependency_mapping(item) for item in raw_items]


def _get_item(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.update_item(**kwargs))


def _required_text(
    item: Mapping[str, object], field: str, error_message: str
) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    return value


def _positive_integer(
    item: Mapping[str, object], field: str, error_message: str
) -> int:
    value = item.get(field)
    if not isinstance(value, (str, bytes, bytearray, _SupportsInt)):
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(error_message) from exc
    if result <= 0:
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    return result


@dataclass(frozen=True, slots=True)
class NotificationPrivatePage:
    items: tuple[NotificationItem, ...]
    cursor: dict[str, str] | None = None
    scanned: int = 0


@dataclass(frozen=True, slots=True)
class DeliveryIntentScope:
    """Validated delivery classification used to bind one logical effect."""

    kind: str
    digest: str
    owner_id: str | None = None
    generation: int | None = None
    classification_seal: str | None = None

    @classmethod
    def private_owner(cls, *, owner_id: str, generation: int) -> DeliveryIntentScope:
        owner = str(owner_id).strip()
        if not owner or type(generation) is not int or generation <= 0:
            raise account_deletion_repo.AccountDeletionConflict(
                "private delivery scope is invalid"
            )
        facts = {"kind": "private_owner", "owner_id": owner, "generation": generation}
        return cls(
            kind="private_owner",
            digest=_delivery_digest(facts),
            owner_id=owner,
            generation=generation,
        )

    @classmethod
    def global_nonprivate(
        cls, *, classification_seal: str
    ) -> DeliveryIntentScope:
        seal = str(classification_seal).strip()
        if not seal:
            raise account_deletion_repo.AccountDeletionConflict(
                "global delivery classification seal is required"
            )
        facts = {"kind": "global_nonprivate", "classification_seal": seal}
        return cls(
            kind="global_nonprivate",
            digest=_delivery_digest(facts),
            classification_seal=seal,
        )


@dataclass(frozen=True, slots=True)
class DeliveryIntentClaim:
    """Opaque exact-version authority for one delivery-intent transition."""

    operation_id: str
    lease_owner: str
    intent_version: int
    lease_expires_at: int
    scope_digest: str
    payload_digest: str


class DeliveryBeginDisposition(StrEnum):
    """Closed outcomes from the final pre-provider delivery transition."""

    BEGUN = "begun"
    CLAIM_LOST = "claim_lost"
    PROVEN_ACCOUNT_DELETED = "proven_account_deleted"
    DEPENDENCY_RETRY = "dependency_retry"


@dataclass(frozen=True, slots=True)
class DeliveryBeginResult:
    """Provider-neutral result of attempting the final delivery CAS."""

    disposition: DeliveryBeginDisposition
    claim: DeliveryIntentClaim | None = None


_DELIVERY_TERMINAL_STATES = frozenset(
    {"accepted", "provider_acceptance_unknown", "canceled_account_deletion"}
)


def _delivery_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _delivery_scope(
    scope: DeliveryIntentScope | None,
    *,
    owner_id: str | None = None,
    generation: int | None = None,
) -> DeliveryIntentScope:
    if isinstance(scope, DeliveryIntentScope):
        return scope
    if owner_id is not None and generation is not None:
        return DeliveryIntentScope.private_owner(
            owner_id=owner_id, generation=generation
        )
    raise account_deletion_repo.AccountDeletionConflict("delivery scope is required")


def _delivery_key(scope: DeliveryIntentScope, operation_id: str) -> dict[str, str]:
    operation = str(operation_id).strip()
    if not operation:
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery operation is required"
        )
    partition = (
        scope.owner_id if scope.kind == "private_owner" else "GLOBAL_NONPRIVATE"
    )
    return {"PK": delivery_intent_pk(str(partition)), "SK": delivery_intent_sk(operation)}


def _delivery_identity_matches(
    item: Mapping[str, object],
    *,
    scope: DeliveryIntentScope,
    operation_id: str,
    payload_digest: str,
) -> bool:
    return bool(
        item.get("operation_id") == operation_id
        and item.get("scope_kind") == scope.kind
        and item.get("scope_digest") == scope.digest
        and item.get("payload_digest") == payload_digest
        and (
            scope.kind != "private_owner"
            or (
                item.get("owner_id") == scope.owner_id
                and item.get("account_fence_generation") == scope.generation
            )
        )
        and (
            scope.kind != "global_nonprivate"
            or item.get("classification_seal") == scope.classification_seal
        )
    )


def _intent_claim(item: Mapping[str, object]) -> DeliveryIntentClaim:
    claim = DeliveryIntentClaim(
        operation_id=_required_text(
            item, "operation_id", "delivery claim is malformed"
        ),
        lease_owner=_required_text(item, "lease_owner", "delivery claim is malformed"),
        intent_version=_positive_integer(
            item, "intent_version", "delivery claim is malformed"
        ),
        lease_expires_at=_positive_integer(
            item, "lease_expires_at", "delivery claim is malformed"
        ),
        scope_digest=_required_text(
            item, "scope_digest", "delivery claim is malformed"
        ),
        payload_digest=_required_text(
            item, "payload_digest", "delivery claim is malformed"
        ),
    )
    if (
        not claim.operation_id
        or not claim.lease_owner
        or claim.intent_version <= 0
        or claim.lease_expires_at <= 0
        or len(claim.scope_digest) != 64
        or len(claim.payload_digest) != 64
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery claim is malformed"
        )
    return claim


def _delivery_conditional_loss(exc: Exception) -> bool:
    return isinstance(exc, (account_deletion_repo.AccountDeletionConflict, db_table.WriteRefused))


def _strong_delivery_intent(
    *, scope: DeliveryIntentScope, claim: DeliveryIntentClaim, table: object
) -> NotificationItem | None:
    response = _get_item(
        table,
        Key=_delivery_key(scope, claim.operation_id),
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def _begun_claim_from_intent(
    item: Mapping[str, object] | None,
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
) -> DeliveryIntentClaim | None:
    if (
        item is None
        or not _delivery_identity_matches(
            item,
            scope=scope,
            operation_id=claim.operation_id,
            payload_digest=claim.payload_digest,
        )
        or item.get("effect_state") != "effect_inflight"
        or item.get("lease_owner") != claim.lease_owner
        or item.get("intent_version") != claim.intent_version + 1
    ):
        return None
    try:
        return _intent_claim(item)
    except account_deletion_repo.AccountDeletionConflict:
        return None


def classify_delivery_transaction_failure(
    exc: Exception,
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    operation_count: int,
    table: object | None = None,
) -> DeliveryBeginResult:
    """Classify a failed begin using ordered reasons and authoritative strong reads.

    A transaction/provider exception is never itself evidence of account deletion.
    The deletion outcome requires both the fence condition refusing the write
    (`AccountNotWritable` from the gateway) and a strong read of the permanent
    fence in a deletion state. `operation_count` is the number of the begin's own
    operations, the fence check not among them.
    """
    target = table or db_table.table()
    try:
        intent = _strong_delivery_intent(scope=scope, claim=claim, table=target)
    except Exception:
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    begun_claim = _begun_claim_from_intent(intent, scope=scope, claim=claim)
    if begun_claim is not None:
        return DeliveryBeginResult(DeliveryBeginDisposition.BEGUN, begun_claim)

    if (
        isinstance(exc, account_deletion_repo.AccountNotWritable)
        and scope.kind == "private_owner"
    ):
        try:
            fence = account_deletion_repo.get_account_fence(
                str(scope.owner_id), table=target
            )
        except Exception:
            return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
        if (
            fence is not None
            and fence.get("user_id") == scope.owner_id
            and fence.get("generation") == scope.generation
            and fence.get("status") in {"deletion_pending", "deleted"}
        ):
            return DeliveryBeginResult(
                DeliveryBeginDisposition.PROVEN_ACCOUNT_DELETED
            )
        # The fence refused but is not deleting this generation: the reasons
        # of the begin's own operations were not kept, so it is tried again.
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    # Only the table's own per-operation reasons say which condition lost; the
    # gateway has already read and sorted them.
    if (
        not isinstance(exc, db_table.WriteRefused)
        or exc.code != "TransactionCanceledException"
        or len(exc.reasons) != operation_count
        or exc.causes - {db_table.ReasonKind.CONDITION_FAILED}
    ):
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
    if exc.failed_conditions:
        return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
    return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)


def notification_pk(event_id: str) -> str:
    return f"NOTIFICATION#{event_id}"


def preference_pk(user_id: str) -> str:
    return f"NOTIFICATION_PREF#{user_id}"


def push_token_pk(user_id: str, token_reference: str) -> str:
    return f"NOTIFICATION_PUSH_TOKEN#{user_id}#{token_reference}"


def delivery_intent_pk(owner_id: str) -> str:
    return f"NOTIFICATION_DELIVERY#{owner_id}"


def delivery_intent_sk(operation_id: str) -> str:
    return f"INTENT#{operation_id}"


def payment_expiry_reminder_pk(parent_id: str) -> str:
    parent = str(parent_id).strip()
    if not parent:
        raise account_deletion_repo.AccountDeletionConflict(
            "payment reminder owner is invalid"
        )
    return f"PAYMENT_EXPIRY_REMINDER#{parent}"


def payment_expiry_reminder_sk(reminder_identity: str) -> str:
    identity = str(reminder_identity).strip()
    if len(identity) != 64:
        raise account_deletion_repo.AccountDeletionConflict(
            "payment reminder identity is invalid"
        )
    return f"REMINDER#{identity}"


# -- Where a notification is found by who it is for (#613) ---------------------------
#
# The bell reads one person's notifications. Finding them by a scan of the whole
# table reads every row of `stoa-main` on every poll, keeps only the first hundred
# notifications of the whole site, and stops answering once the table outgrows the
# scan's page budget. So a notification carries the keys of GSI-SweepPending for
# as long as it is a notification: `sweep_bucket` names who it is for - one
# person, or a whole role when it has no `recipient_id` - and `sweep_due_at` is
# when it was created. The generation sweep (#502), help requests (#608), teacher
# heartbeats (#609) and the upload cleanup (#611) use the same index, each in
# buckets of its own.
#
# Who a notification is for and when it was created never change, so the keys are
# set once, by `put_event`; `update_event` refuses to move them. Account deletion
# replaces the row with a tombstone of allowlisted fields, which has neither key
# and so leaves the index.
INBOX_INDEX = "GSI-SweepPending"
INBOX_INDEX_FIELDS = ("sweep_bucket", "sweep_due_at")
INBOX_SOURCE_FIELDS = frozenset({"recipient_id", "recipient_role", "created_at"})
_INBOX_INDEX_KEY = ("PK", "SK", *INBOX_INDEX_FIELDS)
_INBOX_BUCKET = "notification_inbox"

# The administrators' list is every notification of the site, whoever it is for,
# newest first. A row is in one bucket of GSI-SweepPending - its recipient's - so
# that index cannot hold them all in one place, and the list scanned the table.
# Every notification therefore also carries the keys of GSI-Listing: `listing`
# names the list, the same for all of them, and `listed_at` is when it was
# created. Set once with the inbox keys, and gone with them in a tombstone.
LISTING_INDEX = "GSI-Listing"
LISTING_INDEX_FIELDS = ("listing", "listed_at")
LISTING_NAME = NOTIFICATION_ENTITY
_LISTING_INDEX_KEY = ("PK", "SK", *LISTING_INDEX_FIELDS)
INDEX_FIELDS = (*INBOX_INDEX_FIELDS, *LISTING_INDEX_FIELDS)


def inbox_bucket(*, user_id: str = "", role: str = "") -> str:
    """The index partition of one person's notifications, or of a whole role's."""
    if user_id:
        return f"{_INBOX_BUCKET}#user#{user_id}"
    if role:
        return f"{_INBOX_BUCKET}#role#{role}"
    raise ValueError("an inbox is one person's or one role's")


def index_fields(item: Mapping[str, object]) -> dict[str, str]:
    """The index keys a row carries: a notification's, none for anything else.

    Every notification with a creation time is in the site's list
    (`LISTING_INDEX_FIELDS`). It is in an inbox too (`INBOX_INDEX_FIELDS`) when
    it says who it is for: one with no `recipient_id` is for everyone in its
    `recipient_role`, as `notification_service._visible_to_user` reads it, and
    one that names neither is in no inbox. An index key is never written empty.
    """
    if item.get("entity_type") != NOTIFICATION_ENTITY:
        return {}
    created_at = item.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        return {}
    listed = {"listing": LISTING_NAME, "listed_at": created_at}
    recipient_id = item.get("recipient_id")
    recipient_role = item.get("recipient_role")
    if isinstance(recipient_id, str) and recipient_id:
        bucket = inbox_bucket(user_id=recipient_id)
    elif recipient_id in {None, ""} and isinstance(recipient_role, str) and recipient_role:
        bucket = inbox_bucket(role=recipient_role)
    else:
        return listed
    return {"sweep_bucket": bucket, "sweep_due_at": created_at, **listed}


def carried_index_fields(item: Mapping[str, object]) -> dict[str, object]:
    """The index keys a stored row holds now."""
    return {name: item[name] for name in INDEX_FIELDS if name in item}


def build_notification_write_transaction(
    *,
    item: Mapping[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
) -> list[NotificationItem]:
    """Build one owner-bound write behind the canonical permanent fence."""
    if not owner_id or type(generation) is not int or generation <= 0:
        raise account_deletion_repo.AccountDeletionConflict("notification owner is invalid")
    stored = {
        **dict(item),
        "owner_id": owner_id,
        "account_fence_generation": generation,
    }
    operations: list[NotificationItem] = []
    if mode == "put":
        operations.append(
            {
                "Put": {
                    "Item": stored,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
        )
        return operations
    if mode != "update" or not updates:
        raise ValueError("notification write mode is invalid")
    # A field updated to `None` leaves the row, as a `None` in a put is never
    # written: the gateway drops `None` values from the request, so a `SET` of
    # one would name a value that is not there and the table refuses it.
    assigned = [key for key, value in updates.items() if value is not None]
    removed = [key for key, value in updates.items() if value is None]
    clauses = []
    if assigned:
        clauses.append("SET " + ", ".join(f"#{key}=:{key}" for key in assigned))
    if removed:
        clauses.append("REMOVE " + ", ".join(f"#{key}" for key in removed))
    names = {f"#{key}": key for key in updates}
    values: dict[str, object] = {f":{key}": updates[key] for key in assigned}
    values[":owner"] = owner_id
    operations.append(
        {
            "Update": {
                "Key": {"PK": stored["PK"], "SK": stored["SK"]},
                "UpdateExpression": " ".join(clauses),
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND owner_id=:owner"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }
    )
    return operations


def _generation(owner_id: str, generation: object, table: object) -> int:
    supplied = stored_int(generation)
    if supplied is not None and supplied > 0:
        return supplied
    atomic = db_table.transactional(table)
    if atomic:
        return int(account_deletion_repo.require_active_account_fence(owner_id, table=table)["generation"])
    # Lightweight unit fakes cannot model the permanent fence; transaction
    # builders and real table paths always require the authoritative value.
    return 1


def _persist_private(
    item: NotificationItem,
    *,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
    table: object | None = None,
) -> NotificationItem:
    target = table or db_table.table()
    owner_id = str(item.get("owner_id") or item.get("student_id") or item.get("user_id") or "")
    if not owner_id:
        raise account_deletion_repo.AccountDeletionConflict("notification owner is required")
    generation = _generation(owner_id, item.get("account_fence_generation"), target)
    stored = {**item, "owner_id": owner_id, "account_fence_generation": generation}
    operations = build_notification_write_transaction(
        item=stored,
        owner_id=owner_id,
        generation=generation,
        mode=mode,
        updates=updates,
    )
    # The accounts the row names (its actor, its metadata) are registered by
    # the fenced write from the row as it will stand; their fences do not
    # become conditions of the write (#397, #589).
    db_table.fenced(
        owner_id,
        operations,
        generation=generation,
        rows=[{**stored, **dict(updates or {})}],
        table=target,
    )
    return stored


def put_event(item: NotificationItem) -> NotificationItem:
    event_id = _required_text(item, "event_id", "notification identity is invalid")
    stored = {**item, "PK": notification_pk(event_id), "SK": "META"}
    stored.update(index_fields(stored))
    if stored.get("owner_classification") == "global_nonprivate":
        stored = seal_global_nonprivate_event(stored)
        target = db_table.table()
        _put_item(
            target,
            Item=stored,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        return stored
    return _persist_private(stored)


def get_event(event_id: str) -> NotificationItem | None:
    response = _get_item(
        db_table.table(), Key={"PK": notification_pk(event_id), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def load_delivery_event_strong(
    event_id: str, *, table: object | None = None
) -> NotificationItem | None:
    """Load the canonical event row by base key for provider delivery."""
    canonical_id = str(event_id).strip()
    if not canonical_id:
        return None
    target = table or db_table.table()
    response = _get_item(
        target,
        Key={"PK": notification_pk(canonical_id), "SK": "META"},
        ConsistentRead=True,
    )
    item = _optional_item(response.get("Item"))
    if item is None:
        return None
    if (
        item.get("PK") != notification_pk(canonical_id)
        or item.get("SK") != "META"
        or item.get("entity_type") != NOTIFICATION_ENTITY
        or item.get("event_id") != canonical_id
    ):
        return None
    return dict(item)


def _global_classification_facts(item: Mapping[str, object]) -> NotificationItem:
    return {
        "classification_contract": item.get("classification_contract"),
        "event_id": item.get("event_id"),
        "event_version": item.get("event_version"),
        "event_type": item.get("event_type"),
        "target_type": item.get("target_type"),
        "target_id": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "recipient_role": item.get("recipient_role"),
        "category": item.get("category"),
        "created_at": item.get("created_at"),
        "metadata": item.get("metadata"),
    }


def seal_global_nonprivate_event(item: Mapping[str, object]) -> NotificationItem:
    """Persist an exact content seal for one allowlisted ownerless event."""
    stored = dict(item)
    stored["owner_classification"] = "global_nonprivate"
    stored["classification_contract"] = GLOBAL_NONPRIVATE_CONTRACT_ID
    if not validate_global_nonprivate_event(stored, require_digest=False):
        raise account_deletion_repo.AccountDeletionConflict(
            "global delivery classification is invalid"
        )
    stored["classification_digest"] = _delivery_digest(
        _global_classification_facts(stored)
    )
    return stored


def validate_global_nonprivate_event(
    item: Mapping[str, object], *, require_digest: bool = True
) -> bool:
    contract_id = item.get("classification_contract")
    contract = GLOBAL_NONPRIVATE_DELIVERY_CONTRACTS.get(str(contract_id or ""))
    version = stored_int(item.get("event_version"))
    metadata = item.get("metadata")
    if (
        contract is None
        or item.get("owner_classification") != "global_nonprivate"
        or version is None
        or version <= 0
        or item.get("event_type") not in contract["event_types"]
        or item.get("target_type") not in contract["target_types"]
        or not isinstance(item.get("event_id"), str)
        or not str(item.get("event_id") or "").strip()
        or not isinstance(item.get("target_id"), str)
        or not str(item.get("target_id") or "").strip()
        or not isinstance(item.get("title"), str)
        or not isinstance(item.get("summary"), str)
        or not isinstance(metadata, Mapping)
        or set(metadata) - set(contract["metadata_keys"])
    ):
        return False
    if any(
        item.get(field) not in {None, ""}
        for field in (
            "owner_id",
            "account_fence_generation",
            "recipient_id",
            "actor_id",
            "actor_role",
        )
    ):
        return False
    if not require_digest:
        return True
    digest = item.get("classification_digest")
    return bool(
        isinstance(digest, str)
        and len(digest) == 64
        and digest == _delivery_digest(_global_classification_facts(item))
    )


def update_event(
    event_id: str, updates: NotificationItem
) -> NotificationItem | None:
    existing = get_event(event_id)
    if not existing:
        return None
    if existing.get("owner_classification") == "global_nonprivate":
        raise account_deletion_repo.AccountDeletionConflict(
            "global delivery event is immutable"
        )
    if not updates:
        return existing
    if any(
        updates[name] != existing.get(name)
        for name in (INBOX_SOURCE_FIELDS | set(INDEX_FIELDS)) & updates.keys()
    ):
        # Its place in the index follows from these; nothing moves a notification
        # to another person or another time.
        raise ValueError("a notification's recipient and creation time do not change")
    _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def list_all_events(*, table: object | None = None) -> list[NotificationItem]:
    """Every notification on the table, from every page of the scan.

    For the one-off backfill of #613 and its check; nothing a request calls.
    The administrators' list reads `list_site_events`, a person's `list_inbox`.
    """
    return db_table.rows(
        "scan",
        table=table or db_table.table(),
        FilterExpression=Attr("entity_type").eq(NOTIFICATION_ENTITY),
    )


def list_site_events(
    *,
    want: int,
    keep: Callable[[Mapping[str, object]], bool] | None = None,
    table: object | None = None,
) -> list[NotificationItem]:
    """The site's newest `want` notifications that `keep` admits, newest first (#613).

    A query of the site's list in GSI-Listing, read a page at a time until
    enough are found or the list ends, so what it reads follows how many
    notifications are looked at, not the size of the table. Eventually
    consistent. For the administrators' list; one person's are `list_inbox`.
    """
    if want <= 0:
        return []
    found: list[NotificationItem] = []
    for page in islice(
        db_table.pages(
            "query",
            table=table or db_table.table(),
            key=_LISTING_INDEX_KEY,
            IndexName=LISTING_INDEX,
            KeyConditionExpression=Key("listing").eq(LISTING_NAME),
            ScanIndexForward=False,
        ),
        db_table.SCAN_PAGE_BUDGET,
    ):
        for item in page.items:
            if item.get("entity_type") != NOTIFICATION_ENTITY:
                continue
            if keep is None or keep(item):
                found.append(dict(item))
                if len(found) >= want:
                    return found
        if page.last_key is None:
            return found
    raise db_table.TableUnavailable("page_budget_spent")


def list_inbox(
    *, user_id: str = "", role: str = "", table: object | None = None
) -> list[NotificationItem]:
    """The notifications for this person and for everyone in this role (#613).

    One query of the index per inbox, so what it reads follows how many
    notifications the person has, not the size of the table or how many the
    whole site has. Every page is read: there is no cap that could leave a
    person's own notification out. Unordered across the two inboxes; eventually
    consistent, so a notification written in the last moment may be missing.
    """
    target = table or db_table.table()
    found: list[NotificationItem] = []
    for bucket, for_person in (
        (inbox_bucket(user_id=user_id) if user_id else "", True),
        (inbox_bucket(role=role) if role else "", False),
    ):
        if not bucket:
            continue
        for item in db_table.rows(
            "query",
            table=target,
            key=_INBOX_INDEX_KEY,
            IndexName=INBOX_INDEX,
            KeyConditionExpression=Key("sweep_bucket").eq(bucket),
            ScanIndexForward=False,
        ):
            if item.get("entity_type") != NOTIFICATION_ENTITY:
                continue
            # The row itself says who it is for; the bucket only found it.
            recipient_id = item.get("recipient_id")
            if for_person and recipient_id != user_id:
                continue
            if not for_person and (
                recipient_id not in {None, ""} or item.get("recipient_role") != role
            ):
                continue
            found.append(dict(item))
    return found


def reindex_event(item: Mapping[str, object], *, table: object | None = None) -> bool:
    """Give a notification written before #613 the index keys it calls for.

    For the one-off backfill (`scripts/backfill_notification_inbox_index.py`).
    True when this call wrote them, False when the row already carried exactly
    them. A private notification is written behind its owner's account fence,
    as every other write of it is; one whose owner's deletion got there first is
    refused, and the tombstone that replaces it is in no index. A global one has
    no owner and is written on the condition that it is still that notification.
    """
    fields = index_fields(item)
    if not fields or carried_index_fields(item) == fields:
        return False
    if item.get("owner_classification") == "global_nonprivate":
        try:
            db_table.update(
                table=table or db_table.table(),
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET " + ", ".join(f"#{name} = :{name}" for name in fields),
                ConditionExpression=(
                    "attribute_exists(PK) AND #entity = :entity AND #created = :created"
                ),
                ExpressionAttributeNames={
                    **{f"#{name}": name for name in fields},
                    "#entity": "entity_type",
                    "#created": "created_at",
                },
                ExpressionAttributeValues={
                    **{f":{name}": value for name, value in fields.items()},
                    ":entity": NOTIFICATION_ENTITY,
                    ":created": item.get("created_at"),
                },
            )
        except db_table.WriteRefused as exc:
            raise account_deletion_repo.AccountDeletionConflict(
                "notification changed before it was indexed"
            ) from exc
        return True
    try:
        _persist_private(dict(item), mode="update", updates=fields, table=table)
    except db_table.WriteRefused as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "notification changed before it was indexed"
        ) from exc
    return True


def put_preferences(item: NotificationItem) -> NotificationItem:
    user_id = _required_text(item, "user_id", "notification identity is invalid")
    stored = {**item, "PK": preference_pk(user_id), "SK": "META"}
    existing = get_preferences(user_id)
    if existing:
        values = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        return {**existing, **values} if _persist_private(existing, mode="update", updates=values) else stored
    return _persist_private(stored)


def get_preferences(user_id: str) -> NotificationItem | None:
    response = _get_item(
        db_table.table(), Key={"PK": preference_pk(user_id), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


# -- Where a push device is found (#624) -----------------------------------------------
#
# A push device row is keyed by its person and its reference, so a person's
# devices, and the registrations of one device, were found by a scan of the
# whole table: sending a push read every row of `stoa-main`, and the check that
# a device is not already someone else's looked at the site's first hundred
# device rows only. So a device row carries two places to be found from:
# - GSI-SweepPending: `sweep_bucket` is its person's bucket, `sweep_due_at` when
#   it was registered - for sending to the person's devices.
# - GSI-Listing: `listing` is the list of the registrations of one device,
#   `listed_at` when it was registered - for the ownership check.
#
# The device is where the provider is sent to: the hash of the provider's
# reference when the registration gave one, else `token_hash` (the hash of the
# token, or of the reference). The check reads the lists of both the new
# token's hash and the new reference's hash.
#
# The keys follow from the row and are rewritten with it. Account deletion
# replaces the row with a tombstone of allowlisted fields, which holds none of
# them and so leaves both indexes.
PUSH_TOKEN_USER_INDEX = "GSI-SweepPending"
PUSH_TOKEN_DEVICE_INDEX = "GSI-Listing"
PUSH_TOKEN_INDEX_FIELDS = ("sweep_bucket", "sweep_due_at", "listing", "listed_at")
_PUSH_TOKEN_USER_INDEX_KEY = ("PK", "SK", "sweep_bucket", "sweep_due_at")
_PUSH_TOKEN_DEVICE_INDEX_KEY = ("PK", "SK", "listing", "listed_at")


def push_token_user_bucket(user_id: str) -> str:
    """The GSI-SweepPending partition of one person's push devices."""
    if not user_id:
        raise ValueError("a person's devices are found by their id")
    return f"{PUSH_TOKEN_ENTITY}#user#{user_id}"


def push_token_device_listing(device_key: str) -> str:
    """The GSI-Listing partition of the registrations of one device."""
    if not device_key:
        raise ValueError("a device is found by its key")
    return f"{PUSH_TOKEN_ENTITY}#device#{device_key}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def push_token_device_key(item: Mapping[str, object]) -> str:
    """Where the provider is sent to: the reference's hash, else the token's hash."""
    reference = item.get("provider_token_reference")
    if isinstance(reference, str) and reference:
        return _sha256(reference)
    token_hash = item.get("token_hash")
    return token_hash if isinstance(token_hash, str) else ""


def push_token_lookup_keys(*, token_hash: str, provider_token_reference: str | None) -> set[str]:
    """The device lists a new registration is checked against: its token's and its reference's."""
    keys = {token_hash} if token_hash else set()
    if provider_token_reference:
        keys.add(_sha256(provider_token_reference))
    return keys


def push_token_index_fields(item: Mapping[str, object]) -> dict[str, str]:
    """The index keys a push device row carries; none for any other row.

    Its person's bucket when it names a `user_id`, its device's list when it
    has a token hash or a provider reference, both ordered by when it was
    registered. A row with no registration time is in neither: an index key is
    never written empty.
    """
    if item.get("entity_type") != PUSH_TOKEN_ENTITY:
        return {}
    created_at = item.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        return {}
    fields: dict[str, str] = {}
    user_id = item.get("user_id")
    if isinstance(user_id, str) and user_id:
        fields.update(sweep_bucket=push_token_user_bucket(user_id), sweep_due_at=created_at)
    device_key = push_token_device_key(item)
    if device_key:
        fields.update(listing=push_token_device_listing(device_key), listed_at=created_at)
    return fields


def carried_push_token_index_fields(item: Mapping[str, object]) -> dict[str, object]:
    """The index keys a stored push device row holds now."""
    return {name: item[name] for name in PUSH_TOKEN_INDEX_FIELDS if name in item}


def _push_token_index_updates(
    existing: Mapping[str, object], updates: Mapping[str, object]
) -> dict[str, object]:
    """`updates` with the index keys the row will call for once they are applied."""
    called_for = push_token_index_fields({**existing, **updates})
    return {
        **updates,
        **{name: value for name, value in called_for.items() if existing.get(name) != value},
    }


def put_push_token(item: NotificationItem) -> NotificationItem:
    user_id = _required_text(item, "user_id", "notification identity is invalid")
    token_reference = _required_text(
        item, "token_reference", "notification identity is invalid"
    )
    stored = {
        **item,
        "PK": push_token_pk(user_id, token_reference),
        "SK": "META",
    }
    stored.update(push_token_index_fields(stored))
    existing = get_push_token(user_id, token_reference)
    if existing:
        updates = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        _persist_private(existing, mode="update", updates=updates)
        return {**existing, **updates}
    return _persist_private(stored)


def get_push_token(user_id: str, token_reference: str) -> NotificationItem | None:
    response = _get_item(
        db_table.table(),
        Key={"PK": push_token_pk(user_id, token_reference), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def update_push_token(
    user_id: str, token_reference: str, updates: NotificationItem
) -> NotificationItem | None:
    existing = get_push_token(user_id, token_reference)
    if not existing:
        return None
    if updates:
        updates = _push_token_index_updates(existing, updates)
        _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def list_user_push_tokens(
    user_id: str, *, status: str | None = None, table: object | None = None
) -> list[NotificationItem]:
    """One person's push devices, from GSI-SweepPending (#624).

    One query of the person's bucket, every page of it, so what it reads follows
    how many devices the person registered, not the size of the table.
    Eventually consistent.
    """
    return [
        dict(item)
        for item in db_table.rows(
            "query",
            table=table or db_table.table(),
            key=_PUSH_TOKEN_USER_INDEX_KEY,
            IndexName=PUSH_TOKEN_USER_INDEX,
            KeyConditionExpression=Key("sweep_bucket").eq(push_token_user_bucket(user_id)),
        )
        # The row itself says whose it is; the bucket only found it.
        if item.get("entity_type") == PUSH_TOKEN_ENTITY
        and item.get("user_id") == user_id
        and (status is None or item.get("status") == status)
    ]


def list_device_push_tokens(
    device_keys: set[str], *, table: object | None = None
) -> list[NotificationItem]:
    """Every registration of these devices, whoever made it, from GSI-Listing (#624).

    One query per device, every page of it: what it reads follows how many
    times the device was registered, not the size of the table or how many
    devices the site has. Eventually consistent.
    """
    target = table or db_table.table()
    found: dict[tuple[object, object], NotificationItem] = {}
    for device_key in sorted(key for key in device_keys if key):
        for item in db_table.rows(
            "query",
            table=target,
            key=_PUSH_TOKEN_DEVICE_INDEX_KEY,
            IndexName=PUSH_TOKEN_DEVICE_INDEX,
            KeyConditionExpression=Key("listing").eq(push_token_device_listing(device_key)),
        ):
            if item.get("entity_type") == PUSH_TOKEN_ENTITY:
                found[(item.get("PK"), item.get("SK"))] = dict(item)
    return list(found.values())


def list_all_push_tokens(*, table: object | None = None) -> list[NotificationItem]:
    """Every push device row on the table, from every page of the scan.

    For the one-off backfill of #624 and its check; nothing a request calls.
    """
    return db_table.rows(
        "scan",
        table=table or db_table.table(),
        FilterExpression=Attr("entity_type").eq(PUSH_TOKEN_ENTITY),
    )


def reindex_push_token(item: Mapping[str, object], *, table: object | None = None) -> bool:
    """Give a push device row written before #624 the index keys it calls for.

    For the one-off backfill (`scripts/backfill_push_token_index.py`). True when
    this call wrote them, False when the row already carried exactly them. The
    row is written behind its owner's account fence, as every other write of it
    is; one whose owner's deletion got there first is refused, and the
    tombstone that replaces it is in no index.
    """
    fields = push_token_index_fields(item)
    if not fields or carried_push_token_index_fields(item) == fields:
        return False
    try:
        _persist_private(dict(item), mode="update", updates=fields, table=table)
    except db_table.WriteRefused as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "push device changed before it was indexed"
        ) from exc
    return True


def get_payment_expiry_reminder(
    parent_id: str,
    reminder_identity: str,
    *,
    table: object | None = None,
) -> NotificationItem | None:
    target = table or db_table.table()
    response = _get_item(
        target,
        Key={
            "PK": payment_expiry_reminder_pk(parent_id),
            "SK": payment_expiry_reminder_sk(reminder_identity),
        },
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def list_payment_expiry_reminders(
    parent_id: str, *, table: object | None = None
) -> list[NotificationItem]:
    target = table or db_table.table()
    response = _query(
        target,
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": payment_expiry_reminder_pk(parent_id)},
        ConsistentRead=True,
    )
    return [
        item
        for item in _response_items(response)
        if item.get("entity_type") == PAYMENT_EXPIRY_REMINDER_ENTITY
        and item.get("parent_id") == parent_id
        and item.get("owner_id") == parent_id
    ]


def put_payment_expiry_reminder(
    item: Mapping[str, object], *, table: object | None = None
) -> NotificationItem:
    target = table or db_table.table()
    parent_id = _required_text(
        item, "parent_id", "payment reminder owner is invalid"
    )
    identity = _required_text(
        item, "reminder_identity", "payment reminder identity is invalid"
    )
    key = {
        "PK": payment_expiry_reminder_pk(parent_id),
        "SK": payment_expiry_reminder_sk(identity),
    }
    existing = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if existing is not None:
        if (
            existing.get("entity_type") != PAYMENT_EXPIRY_REMINDER_ENTITY
            or existing.get("schema_version") != "payment_expiry_reminder.v1"
            or existing.get("parent_id") != parent_id
            or existing.get("reminder_identity") != identity
            or existing.get("payment_method_digest")
            != item.get("payment_method_digest")
            or existing.get("exp_month") != item.get("exp_month")
            or existing.get("exp_year") != item.get("exp_year")
        ):
            raise account_deletion_repo.AccountDeletionConflict(
                "payment reminder identity changed"
            )
        return existing
    generation = _generation(
        parent_id, item.get("account_fence_generation"), target
    )
    stored: NotificationItem = {
        **dict(item),
        **key,
        "entity_type": PAYMENT_EXPIRY_REMINDER_ENTITY,
        "schema_version": "payment_expiry_reminder.v1",
        "owner_id": parent_id,
        "account_fence_generation": generation,
    }
    try:
        db_table.fenced(
            parent_id,
            build_notification_write_transaction(
                item=stored,
                owner_id=parent_id,
                generation=generation,
            ),
            generation=generation,
            table=target,
        )
    except Exception as exc:
        if not _delivery_conditional_loss(exc):
            raise
        replay = get_payment_expiry_reminder(
            parent_id, identity, table=target
        )
        if replay is None:
            raise
        return replay
    return stored


def _update_payment_expiry_reminder(
    parent_id: str,
    reminder_identity: str,
    updates: Mapping[str, object],
    *,
    table: object | None = None,
) -> NotificationItem | None:
    target = table or db_table.table()
    current = get_payment_expiry_reminder(
        parent_id, reminder_identity, table=target
    )
    if current is None:
        return None
    generation = _generation(
        parent_id, current.get("account_fence_generation"), target
    )
    operations = build_notification_write_transaction(
        item=current,
        owner_id=parent_id,
        generation=generation,
        mode="update",
        updates=updates,
    )
    db_table.fenced(
        parent_id,
        operations,
        generation=generation,
        rows=owner_registry.rows_after(current, operations),
        table=target,
    )
    return {**current, **dict(updates)}


def resolve_payment_expiry_reminder(
    parent_id: str,
    reminder_identity: str,
    *,
    resolved_at: str,
    table: object | None = None,
) -> NotificationItem | None:
    target = table or db_table.table()
    return _update_payment_expiry_reminder(
        parent_id,
        reminder_identity,
        {"status": "resolved", "resolved_at": resolved_at, "updated_at": resolved_at},
        table=target,
    )


def mark_payment_expiry_reminder_notified(
    parent_id: str,
    reminder_identity: str,
    *,
    notified_at: str,
    table: object | None = None,
) -> NotificationItem | None:
    target = table or db_table.table()
    return _update_payment_expiry_reminder(
        parent_id,
        reminder_identity,
        {"status": "notified", "notified_at": notified_at, "updated_at": notified_at},
        table=target,
    )


def register_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str,
    channel: str,
    event_ids: list[str],
    payload_digest: str,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or db_table.table()
    key = _delivery_key(scope, operation_id)
    existing = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if existing:
        if not _delivery_identity_matches(
            existing,
            scope=scope,
            operation_id=operation_id,
            payload_digest=payload_digest,
        ) or existing.get("channel") != channel or existing.get("event_ids") != event_ids:
            raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
        return dict(existing)
    item: NotificationItem = {
        **key,
        "entity_type": DELIVERY_INTENT_ENTITY,
        "schema_version": "notification-delivery-intent.v2",
        "operation_id": operation_id,
        "scope_kind": scope.kind,
        "scope_digest": scope.digest,
        "channel": channel,
        "event_ids": list(event_ids),
        "payload_digest": payload_digest,
        "intent_version": 1,
        "effect_state": "registered",
        "status": "registered",
        "outcome_status": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    if scope.kind == "private_owner":
        item.update(
            owner_id=scope.owner_id,
            account_fence_generation=scope.generation,
        )
    else:
        item["classification_seal"] = scope.classification_seal
    if scope.kind == "private_owner":
        db_table.fenced(
            str(scope.owner_id),
            build_notification_write_transaction(
                item=item,
                owner_id=str(scope.owner_id),
                generation=int(scope.generation or 0),
                mode="put",
            ),
            generation=int(scope.generation or 0),
            table=target,
        )
    else:
        _put_item(
            target,
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    return item


def claim_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str,
    payload_digest: str | None = None,
    now_epoch: int | None = None,
    lease_expires_at: int,
    lease_owner: str | None = None,
    now_iso: str | None = None,
    table: object | None = None,
) -> DeliveryIntentClaim | None:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or db_table.table()
    key = _delivery_key(scope, operation_id)
    current = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if current is None:
        return None
    digest = str(payload_digest or current.get("payload_digest") or "")
    if not _delivery_identity_matches(
        current,
        scope=scope,
        operation_id=operation_id,
        payload_digest=digest,
    ):
        raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
    if type(now_epoch) is not int:
        from time import time

        now_epoch = int(time())
    if now_epoch < 0 or type(lease_expires_at) is not int or lease_expires_at <= now_epoch:
        raise account_deletion_repo.AccountDeletionConflict("delivery lease time is invalid")
    opaque_owner = str(lease_owner or f"delivery-lease-{uuid4().hex}").strip()
    if not opaque_owner:
        raise account_deletion_repo.AccountDeletionConflict("delivery lease owner is invalid")
    if scope.kind == "private_owner":
        account_deletion_repo.require_active_account_fence(
            str(scope.owner_id), int(scope.generation or 0), table=target
        )
    try:
        current_version = _positive_integer(
            current, "intent_version", "delivery claim is malformed"
        )
        attributes = db_table.update(
            table=target,
            Key=key,
            UpdateExpression=(
                "SET #effect=:pre_effect, #status=:pre_effect, "
                "lease_owner=:lease, lease_expires_at=:expiry, "
                "intent_version=intent_version + :one, updated_at=:now"
            ),
            ConditionExpression=(
                "(#effect=:registered OR (#effect=:pre_effect AND "
                "lease_expires_at < :now_epoch)) AND scope_digest=:scope "
                "AND payload_digest=:payload AND intent_version=:version"
            ),
            ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
            ExpressionAttributeValues={
                ":registered": "registered",
                ":pre_effect": "claimed_pre_effect",
                ":scope": scope.digest,
                ":payload": digest,
                ":version": current_version,
                ":lease": opaque_owner,
                ":expiry": lease_expires_at,
                ":now_epoch": now_epoch,
                ":one": 1,
                ":now": now_iso or "",
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _delivery_conditional_loss(exc):
            return None
        raise
    # Nothing handed back: the claim is what was asked for.
    if not attributes:
        current_version = _positive_integer(
            current, "intent_version", "delivery claim is malformed"
        )
        attributes = {
            **dict(current),
            "lease_owner": opaque_owner,
            "lease_expires_at": lease_expires_at,
            "intent_version": current_version + 1,
        }
    return _intent_claim(attributes)


def delivery_intent_sendable(
    *,
    scope: DeliveryIntentScope | None = None,
    claim: DeliveryIntentClaim | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str | None = None,
    lease_owner: str | None = None,
    table: object | None = None,
) -> bool:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    operation = claim.operation_id if claim is not None else str(operation_id or "")
    target = table or db_table.table()
    item = _optional_item(
        _get_item(
            target,
            Key=_delivery_key(scope, operation),
            ConsistentRead=True,
        ).get("Item")
    )
    if item is None:
        return False
    if claim is not None:
        return bool(
            item.get("effect_state") == "claimed_pre_effect"
            and item.get("lease_owner") == claim.lease_owner
            and item.get("intent_version") == claim.intent_version
            and item.get("scope_digest") == claim.scope_digest == scope.digest
            and item.get("payload_digest") == claim.payload_digest
        )
    return bool(
        item.get("effect_state") in {"claimed_pre_effect", "claimed"}
        and item.get("lease_owner") == lease_owner
    )


def begin_delivery_effect(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    now_iso: str,
    table: object | None = None,
) -> DeliveryBeginResult:
    """Durably cross the final exact CAS immediately before provider mutation."""
    scope = _delivery_scope(scope)
    if claim.scope_digest != scope.digest:
        return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
    target = table or db_table.table()
    condition_expression = (
        "#effect=:pre_effect AND lease_owner=:lease AND "
        "intent_version=:version AND scope_digest=:scope AND "
        "payload_digest=:payload"
    )
    expression_values: NotificationItem = {
        ":pre_effect": "claimed_pre_effect",
        ":inflight": "effect_inflight",
        ":lease": claim.lease_owner,
        ":version": claim.intent_version,
        ":scope": claim.scope_digest,
        ":payload": claim.payload_digest,
        ":now": now_iso,
        ":one": 1,
    }
    event_checks: list[NotificationItem] = []
    if scope.kind != "private_owner":
        intent = _optional_item(
            _get_item(
                target,
                Key=_delivery_key(scope, claim.operation_id),
                ConsistentRead=True,
            ).get("Item")
        )
        raw_event_ids = intent.get("event_ids") if intent is not None else None
        if not isinstance(raw_event_ids, list) or not raw_event_ids:
            raise account_deletion_repo.AccountDeletionConflict(
                "global delivery event set is invalid"
            )
        event_ids: list[str] = []
        for raw_event_id in raw_event_ids:
            if not isinstance(raw_event_id, str) or not raw_event_id:
                raise account_deletion_repo.AccountDeletionConflict(
                    "global delivery event set is invalid"
                )
            event_ids.append(raw_event_id)
        for event_id in event_ids:
            event = load_delivery_event_strong(event_id, table=target)
            if (
                event is None
                or not validate_global_nonprivate_event(event)
                or event.get("classification_digest") != scope.classification_seal
            ):
                raise account_deletion_repo.AccountDeletionConflict(
                    "global delivery classification changed"
                )
            event_checks.append(
                {
                    "ConditionCheck": {
                        "Key": {"PK": notification_pk(event_id), "SK": "META"},
                        "ConditionExpression": (
                            "owner_classification=:global_kind AND "
                            "classification_contract=:contract AND "
                            "classification_digest=:classification_seal AND "
                            "event_version=:event_version"
                        ),
                        "ExpressionAttributeValues": {
                            ":global_kind": "global_nonprivate",
                            ":contract": GLOBAL_NONPRIVATE_CONTRACT_ID,
                            ":classification_seal": scope.classification_seal,
                            ":event_version": event["event_version"],
                        },
                    }
                }
            )
        condition_expression += (
            " AND scope_kind=:global_kind AND classification_seal=:classification_seal"
        )
        expression_values.update(
            {
                ":global_kind": "global_nonprivate",
                ":classification_seal": scope.classification_seal,
            }
        )
    update_details: NotificationItem = {
        "Key": _delivery_key(scope, claim.operation_id),
        "UpdateExpression": (
            "SET #effect=:inflight, #status=:inflight, effect_started_at=:now, "
            "intent_version=intent_version + :one"
        ),
        "ConditionExpression": condition_expression,
        "ExpressionAttributeNames": {
            "#effect": "effect_state",
            "#status": "status",
        },
        "ExpressionAttributeValues": expression_values,
    }
    update: NotificationItem = {"Update": update_details}
    operations = [*event_checks, update]
    try:
        if scope.kind == "private_owner":
            db_table.fenced(
                str(scope.owner_id),
                operations,
                generation=int(scope.generation or 0),
                table=target,
            )
        else:
            db_table.transact(operations, table=target)
    except Exception as exc:
        return classify_delivery_transaction_failure(
            exc,
            scope=scope,
            claim=claim,
            operation_count=len(operations),
            table=target,
        )
    return DeliveryBeginResult(
        DeliveryBeginDisposition.BEGUN,
        DeliveryIntentClaim(
            operation_id=claim.operation_id,
            lease_owner=claim.lease_owner,
            intent_version=claim.intent_version + 1,
            lease_expires_at=claim.lease_expires_at,
            scope_digest=claim.scope_digest,
            payload_digest=claim.payload_digest,
        ),
    )


def recover_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    operation_id: str,
    payload_digest: str,
    now_epoch: int,
    expected_claim: DeliveryIntentClaim | None = None,
    now_iso: str | None = None,
    table: object | None = None,
) -> NotificationItem:
    """Classify replay and terminalize an observed ambiguous inflight effect."""
    scope = _delivery_scope(scope)
    target = table or db_table.table()
    key = _delivery_key(scope, operation_id)
    item = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if item is None or not _delivery_identity_matches(
        item,
        scope=scope,
        operation_id=operation_id,
        payload_digest=payload_digest,
    ):
        raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
    state = str(item.get("effect_state") or item.get("status") or "")
    if expected_claim is not None:
        current_claim = _intent_claim(item)
        if current_claim != expected_claim:
            raise account_deletion_repo.AccountDeletionConflict("stale delivery claim")
    if state in _DELIVERY_TERMINAL_STATES:
        return {"status": state}
    if state != "effect_inflight":
        return dict(item)
    observed = _intent_claim(item)
    try:
        attributes = db_table.update(
            table=target,
            Key=key,
            UpdateExpression=(
                "SET #effect=:unknown, #status=:unknown, outcome_status=:unknown, "
                "intent_version=intent_version + :one, updated_at=:now "
                "REMOVE lease_owner, lease_expires_at"
            ),
            ConditionExpression=(
                "#effect=:inflight AND lease_owner=:lease AND intent_version=:version "
                "AND scope_digest=:scope AND payload_digest=:payload"
            ),
            ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
            ExpressionAttributeValues={
                ":inflight": "effect_inflight",
                ":unknown": "provider_acceptance_unknown",
                ":lease": observed.lease_owner,
                ":version": observed.intent_version,
                ":scope": observed.scope_digest,
                ":payload": observed.payload_digest,
                ":one": 1,
                ":now": now_iso or "",
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _delivery_conditional_loss(exc):
            raise account_deletion_repo.AccountDeletionConflict(
                "delivery recovery claim lost"
            ) from exc
        raise
    return _dependency_mapping(attributes) if attributes else {
        "status": "provider_acceptance_unknown"
    }


def cancel_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    return _finish_delivery_intent(
        scope=scope,
        claim=claim,
        status="canceled_account_deletion",
        expected_state="claimed_pre_effect",
        now_iso=now_iso,
        table=table,
    )


def complete_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    claim: DeliveryIntentClaim | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str | None = None,
    lease_owner: str | None = None,
    status: str,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    legacy = claim is None
    if status not in _DELIVERY_TERMINAL_STATES and not (legacy and status == "rejected"):
        raise account_deletion_repo.AccountDeletionConflict("invalid delivery completion")
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or db_table.table()
    item: NotificationItem | None = None
    if claim is None:
        item = _optional_item(
            _get_item(
                target,
                Key=_delivery_key(scope, str(operation_id or "")),
                ConsistentRead=True,
            ).get("Item")
        )
        if item is None or item.get("lease_owner") != lease_owner:
            raise account_deletion_repo.AccountDeletionConflict("stale delivery claim")
        claim = _intent_claim(item)
    return _finish_delivery_intent(
        scope=scope,
        claim=claim,
        status=status,
        expected_state=(
            str(item.get("effect_state") or item.get("status") or "")
            if legacy and item is not None
            else "effect_inflight"
        ),
        now_iso=now_iso,
        table=target,
    )


def _finish_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    status: str,
    expected_state: str,
    now_iso: str,
    table: object | None,
) -> NotificationItem:
    target = table or db_table.table()
    response = _update_item(
        target,
        Key=_delivery_key(scope, claim.operation_id),
        UpdateExpression=(
            "SET #effect=:status, #status=:status, outcome_status=:status, "
            "intent_version=intent_version + :one, updated_at=:now "
            "REMOVE lease_owner, lease_expires_at"
        ),
        ConditionExpression=(
            "#effect=:expected AND lease_owner=:lease AND intent_version=:version "
            "AND scope_digest=:scope AND payload_digest=:payload"
        ),
        ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":expected": expected_state,
            ":now": now_iso,
            ":lease": claim.lease_owner,
            ":version": claim.intent_version,
            ":scope": claim.scope_digest,
            ":payload": claim.payload_digest,
            ":one": 1,
        },
        ReturnValues="ALL_NEW",
    )
    attributes = response.get("Attributes")
    return (
        {"status": status}
        if not attributes
        else _dependency_mapping(attributes)
    )


def scan_notification_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> NotificationPrivatePage:
    target = table or db_table.table()
    current = cursor
    seen: set[tuple[str, str]] = set()
    found: list[NotificationItem] = []
    scanned = 0
    for page in account_deletion_repo.sweep_pages(
        "notification",
        table=target,
        cursor=cursor,
        page_limit=100,
        maximum_pages=max(maximum_pages, 1),
    ):
        items = page.items
        scanned += len(items)
        found.extend(
            dict(item)
            for item in items
            if item.get("entity_type") in NOTIFICATION_PRIVATE_ROW_REGISTRY
            and (
                _targets_owner(item, owner_id)
                or _targets_identity_reference(item, owner_id)
            )
            and not _already_scrubbed(item)
        )
        if page.last_key is None:
            return NotificationPrivatePage(tuple(found), None, scanned)
        current = page.last_key
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeated notification cursor")
        seen.add(identity)
    return NotificationPrivatePage(tuple(found), current, scanned)


def scrub_notification_private_row(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> None:
    if _targets_owner(item, owner_id):
        _replace_notification_owner_tombstone(
            item,
            owner_id=owner_id,
            generation=generation,
            now_iso=now_iso,
            table=table,
        )
        return
    if _targets_identity_reference(item, owner_id):
        scrub_notification_identity_references(
            item,
            owner_id=owner_id,
            generation=generation,
            table=table,
        )
        return
    raise account_deletion_repo.AccountDeletionConflict("notification owner changed")


def _replace_notification_owner_tombstone(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None,
) -> None:
    if not _targets_owner(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict("notification owner changed")
    target = table or db_table.table()
    entity = str(item.get("entity_type") or "notification")
    status = str(item.get("status") or "")
    tombstone = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": f"{entity}_deletion_tombstone",
        "schema_version": "notification-deletion-tombstone.v1",
        "status": status if entity == DELIVERY_INTENT_ENTITY and status in _EXTERNAL_RECEIPT_STATES else "deleted",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
    }
    for field in ("event_id", "summary_id", "operation_id", "channel", "created_at", "accepted_at"):
        if item.get(field) is not None:
            tombstone[field] = item[field]
    tombstone = {key: value for key, value in tombstone.items() if key in NOTIFICATION_TOMBSTONE_ALLOWLIST}
    hook = getattr(target, "replace_notification_tombstone", None)
    if callable(hook):
        hook(dict(item), tombstone, owner_id, generation)
        return
    db_table.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK) AND owner_id=:owner",
                    "ExpressionAttributeValues": {":owner": owner_id},
                }
            },
        ],
        table=target,
    )


def scrub_notification_identity_references(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    table: object | None = None,
) -> None:
    """Remove one foreign identity without mutating recipient-owned evidence."""
    if _targets_owner(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification owner requires tombstone"
        )
    if not _targets_identity_reference(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification identity changed"
        )

    pk = _required_identity_coordinate(item.get("PK"), "PK")
    sk = _required_identity_coordinate(item.get("SK"), "SK")
    entity = _required_identity_coordinate(item.get("entity_type"), "entity type")
    schema = _required_identity_coordinate(item.get("schema_version"), "schema version")
    status = _required_identity_coordinate(item.get("status"), "status")
    version = stored_int(item.get("event_version"))
    if version is None or version <= 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "notification version is malformed"
        )

    metadata = item.get("metadata")
    if not isinstance(metadata, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification metadata is malformed"
        )
    metadata_snapshot = _dependency_mapping(metadata)
    # Only its refusal is wanted: metadata that does not encode is malformed.
    _notification_metadata_digest(metadata_snapshot)
    # Where the catalog says the row mentions the account: fields in
    # `metadata`, and on the row itself its `actor_id`.
    paths = data_catalog.referenced_paths(item, owner_id)
    metadata_fields = {
        path.removeprefix("metadata.") for path in paths if path.startswith("metadata.")
    }
    direct_fields = [path for path in paths if "." not in path]
    if set(direct_fields) - {"actor_id"} or any(
        "." in field for field in metadata_fields
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification reference field has no scrub"
        )
    clean_metadata = {
        key: value
        for key, value in metadata_snapshot.items()
        if not (key in metadata_fields and value == owner_id)
    }
    direct_match = "actor_id" in direct_fields

    target = table or db_table.table()
    condition = (
        "PK=:pk AND SK=:sk AND entity_type=:entity AND schema_version=:schema "
        "AND event_version=:version AND #status=:status AND metadata=:metadata"
    )
    values: dict[str, object] = {
        ":pk": pk,
        ":sk": sk,
        ":entity": entity,
        ":schema": schema,
        ":version": version,
        ":next_version": version + 1,
        ":status": status,
        ":metadata": metadata_snapshot,
        ":clean_metadata": clean_metadata,
    }
    update = "SET metadata=:clean_metadata, event_version=:next_version"
    if direct_match:
        condition += " AND actor_id=:identity"
        values[":identity"] = owner_id
        update += " REMOVE actor_id"

    db_table.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Update": {
                    "Key": {"PK": pk, "SK": sk},
                    "UpdateExpression": update,
                    "ConditionExpression": condition,
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": values,
                }
            },
        ],
        table=target,
    )


def _required_identity_coordinate(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise account_deletion_repo.AccountDeletionConflict(
            f"notification {name} is malformed"
        )
    return value


def _notification_metadata_digest(metadata: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            dict(metadata),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "notification metadata is malformed"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _targets_owner(item: Mapping[str, object], owner_id: str) -> bool:
    """Whether the notification row is `owner_id`'s own, by the data type catalog."""
    return (
        item.get("entity_type") in NOTIFICATION_PRIVATE_ROW_REGISTRY
        and data_catalog.owns(item, account_deletion_repo.deletion_account(owner_id))
    )


def _targets_identity_reference(
    item: Mapping[str, object], owner_id: str
) -> bool:
    """Whether the notification row only mentions `owner_id` (#574), by the catalog."""
    return item.get("entity_type") in NOTIFICATION_PRIVATE_ROW_REGISTRY and (
        data_catalog.role_of(item, account_deletion_repo.deletion_account(owner_id))
        == data_catalog.REFERENCE
    )


def _already_scrubbed(item: Mapping[str, object]) -> bool:
    return str(item.get("entity_type") or "").endswith("_deletion_tombstone")
