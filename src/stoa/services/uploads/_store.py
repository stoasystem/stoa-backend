"""The upload rows: `UPLOAD#{id}` / `META` and its parts, `PART#{n:06d}`.

The only module that builds an upload key or writes an upload row. Every
state change goes through `_transition` or `_fenced_transition`: a conditional
update on the owner, the state and the version, the fenced one also on the
operation fence a takeover replaces. The shared DynamoDB helpers stay in
`attachment_repo` until "one table gateway" (#210).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from botocore.exceptions import ClientError

from stoa.db import table as db_table
from stoa.config import UPLOAD_ROW_RETENTION_SECONDS
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.models.attachment import UploadStatus
from stoa.db.repositories.attachment_repo import (
    AttachmentRepositoryConflict,
    _conditional,
    _get_item,
    _mapping,
    _optional_mapping,
    _put_item,
    _query,
    _require_canonical_sha256,
    _require_positive_integer,
    _require_provider_coordinate,
    _require_provider_sha256,
    _required_integer,
    _required_text,
    _scan,
    _update_item,
    list_owner_attachment_items,
    retention_fence_key,
    transact,
)



def _table() -> object:
    """The main table, reached as `attachment_repo` reaches it until one table gateway (#210)."""
    return attachment_repo.get_table()

def upload_key(upload_id: str) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": "META"}


def upload_part_key(upload_id: str, part_number: int) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": f"PART#{part_number:06d}"}


def create_upload_intent(item: dict[str, object], *, table: object | None = None) -> None:
    owner_id = str(item.get("owner_id") or "")
    generation = item.get("account_fence_generation")
    if type(generation) is not int or generation <= 0:
        raise AttachmentRepositoryConflict("conditional_conflict")
    upload_id = _required_text(item.get("upload_id"))
    try:
        db_table.fenced(
            owner_id,
            [
                {
                    "Put": {
                        "Item": {**upload_key(upload_id), **item},
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
            ],
            generation=generation,
            table=table or _table(),
        )
    except (
        account_deletion_repo.AccountDeletionConflict,
        db_table.WriteRefused,
        db_table.TableUnavailable,
    ) as exc:
        raise AttachmentRepositoryConflict("conditional_conflict") from exc


def prepare_staging_issuance(item: dict[str, object], *, table: object | None = None) -> None:
    """Persist the never-reused staging coordinate before provider mutation."""
    required = {
        "staging_object_key",
        "operation_kind",
        "operation_fence",
        "operation_lease_expires_at",
    }
    if item.get("status") != "issuing" or not required.issubset(item):
        raise AttachmentRepositoryConflict("invalid_operation_state")
    create_upload_intent(item, table=table)


def record_staging_multipart(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    multipart_upload_id: object,
    table: object | None = None,
) -> bool:
    multipart_upload_id = _require_provider_coordinate(multipart_upload_id)
    return _fenced_transition(
        upload_id, owner_id, "issuing", "pending_upload", version, operation_fence,
        attributes={"multipart_upload_id": multipart_upload_id},
        remove_operation=True, table=table,
    )


def mark_upload_issuance_failed(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    table: object | None = None,
) -> bool:
    """An issuance that failed hands its row to cleanup: a multipart may exist."""
    return _transition(
        upload_id,
        owner_id,
        "issuing",
        "cleanup_pending",
        version,
        None,
        attributes={"validation_failure": "service_unavailable"},
        table=table,
    )


def get_upload_part(
    upload_id: str, part_number: int, *, table: object | None = None
) -> dict[str, object] | None:
    response = _get_item(table or _table(),
        Key=upload_part_key(upload_id, part_number), ConsistentRead=True
    )
    return _optional_mapping(response.get("Item"))


PRESIGNED_PART_OWNER = "presigned"


def pin_upload_part(
    upload_id: str,
    part_number: int,
    checksum_sha256: str,
    length: int,
    now_epoch: int,
    *,
    table: object | None = None,
) -> dict[str, object]:
    """Fix the bytes a part may hold before a URL is signed for it.

    The browser writes the part on S3 itself, so there is no lease to hold: the
    row only pins the length and SHA-256 the URL is signed for, and a request for
    the same part with other bytes is a `chunk_conflict`. Completion records what
    S3 acknowledged against this row.
    """
    part_number = _require_positive_integer(part_number)
    checksum_sha256 = _require_canonical_sha256(checksum_sha256)
    length = _require_positive_integer(length)
    if isinstance(now_epoch, bool) or not isinstance(now_epoch, int) or now_epoch < 0:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    target = table or _table()
    intent = get_upload_intent(upload_id, table=target)
    if intent is None:
        raise AttachmentRepositoryConflict("conditional_conflict")
    intent_usable_until = usable_until(intent)
    if intent_usable_until <= now_epoch:
        raise AttachmentRepositoryConflict("conditional_conflict")
    item = {
        **upload_part_key(upload_id, part_number),
        "upload_id": upload_id,
        "part_number": part_number,
        "status": "uploading",
        "checksum_sha256": checksum_sha256,
        "content_length": length,
        "lease_owner": PRESIGNED_PART_OWNER,
        "expires_at": intent_usable_until + UPLOAD_ROW_RETENTION_SECONDS,
        "attempt": 1,
    }
    try:
        _put_item(target,
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        return item
    except ClientError as exc:
        if not _conditional(exc):
            raise AttachmentRepositoryConflict("dependency_failure") from None
    current = get_upload_part(upload_id, part_number, table=target)
    if not current:
        raise AttachmentRepositoryConflict("dependency_failure")
    if (
        current.get("checksum_sha256") != checksum_sha256
        or _required_integer(current.get("content_length", -1)) != length
    ):
        raise AttachmentRepositoryConflict("chunk_conflict")
    return current


def complete_upload_part(
    upload_id: str,
    part_number: int,
    lease_owner: str,
    *,
    provider_etag: str,
    provider_checksum: str,
    expected_checksum_sha256: str,
    content_length: int,
    table: object | None = None,
) -> bool:
    part_number = _require_positive_integer(part_number)
    _require_provider_coordinate(lease_owner)
    provider_etag = _require_provider_coordinate(provider_etag)
    expected_checksum_sha256 = _require_canonical_sha256(expected_checksum_sha256)
    provider_checksum = _require_provider_sha256(
        provider_checksum, expected_hex=expected_checksum_sha256
    )
    content_length = _require_positive_integer(content_length)
    try:
        _update_item(table or _table(),
            Key=upload_part_key(upload_id, part_number),
            UpdateExpression=(
                "SET #status=:completed, provider_etag=:etag, "
                "provider_checksum=:provider_checksum REMOVE lease_expires_at"
            ),
            ConditionExpression=(
                "#status=:uploading AND lease_owner=:owner AND "
                "checksum_sha256=:checksum AND content_length=:length"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":uploading": "uploading",
                ":completed": "completed",
                ":owner": lease_owner,
                ":etag": provider_etag,
                ":provider_checksum": provider_checksum,
                ":checksum": expected_checksum_sha256,
                ":length": content_length,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def list_upload_parts(upload_id: str, *, table: object | None = None) -> list[dict[str, object]]:
    from boto3.dynamodb.conditions import Key

    response = _query(table or _table(),
        KeyConditionExpression=Key("PK").eq(f"UPLOAD#{upload_id}") & Key("SK").begins_with("PART#"),
        ConsistentRead=True,
    )
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    items = [
        _mapping(item, category="invalid_provider_acknowledgement")
        for item in raw_items
    ]
    validated: list[dict[str, object]] = []
    seen: set[int] = set()
    for item in items:
        part_number = _require_positive_integer(item.get("part_number"))
        if part_number in seen:
            raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
        seen.add(part_number)
        _require_canonical_sha256(item.get("checksum_sha256"))
        _require_positive_integer(item.get("content_length"))
        if item.get("status") == "completed":
            _require_provider_coordinate(item.get("provider_etag"))
            _require_provider_sha256(
                item.get("provider_checksum"),
                expected_hex=_require_canonical_sha256(item.get("checksum_sha256")),
            )
        validated.append(item)
    return sorted(
        validated,
        key=lambda item: _require_positive_integer(item.get("part_number")),
    )


def claim_staging_assembly(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    operation_fence: str,
    multipart_upload_id: str,
    ordered_part_count: int,
    part_ledger_digest: str,
    table: object | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    multipart_upload_id = _require_provider_coordinate(multipart_upload_id)
    ordered_part_count = _require_positive_integer(ordered_part_count)
    part_ledger_digest = _require_canonical_sha256(part_ledger_digest)
    return _transition(
        upload_id,
        owner_id,
        "pending_upload",
        "assembling",
        version,
        now_epoch,
        attributes={
            "operation_kind": "staging_assembly",
            "operation_fence": operation_fence,
            "operation_lease_expires_at": now_epoch + 120,
            "multipart_upload_id": multipart_upload_id,
            "assembly_part_count": ordered_part_count,
            "assembly_ledger_digest": part_ledger_digest,
            "operation_takeover_count": 0,
        },
        table=table,
    )


def recover_staging_completion(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    staging_version_id: object,
    staging_etag: object,
    table: object | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    staging_version_id = _require_provider_coordinate(staging_version_id)
    staging_etag = _require_provider_coordinate(staging_etag)
    return _fenced_transition(
        upload_id, owner_id, "assembling", "validating", version, operation_fence,
        attributes={
            "staging_version_id": staging_version_id,
            "staging_etag": staging_etag,
        },
        remove_operation=True, table=table,
    )


def claim_stale_upload_operation(
    upload_id: str,
    owner_id: str,
    version: int,
    operation_kind: str,
    previous_fence: str,
    new_fence: str,
    now_epoch: int,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    """Bounded lease takeover that fences every pre-restart worker."""
    try:
        response = _update_item(table or _table(),
            Key=upload_key(upload_id),
            UpdateExpression=(
                "SET operation_fence=:new_fence, operation_lease_expires_at=:lease, "
                "operation_takeover_count=if_not_exists(operation_takeover_count,:zero)+:one, "
                "#version=:next"
            ),
            ConditionExpression=(
                "#owner=:owner AND #version=:version AND operation_kind=:kind AND "
                "operation_fence=:previous_fence AND operation_lease_expires_at<=:now AND "
                "(attribute_not_exists(operation_takeover_count) OR operation_takeover_count<:max)"
            ),
            ExpressionAttributeNames={"#owner": "owner_id", "#version": "version"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":version": version,
                ":next": version + 1,
                ":kind": operation_kind,
                ":previous_fence": previous_fence,
                ":new_fence": new_fence,
                ":now": now_epoch,
                ":lease": now_epoch + 120,
                ":zero": 0,
                ":one": 1,
                ":max": 2,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if _conditional(exc):
            return None
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return _optional_mapping(response.get("Attributes"))


def get_upload_intent(upload_id: str, *, table: object | None = None) -> dict[str, object] | None:
    response = _get_item(table or _table(), Key=upload_key(upload_id), ConsistentRead=True)
    return _optional_mapping(response.get("Item"))


def list_upload_cleanup_candidates(
    now_epoch: int,
    *,
    limit: int,
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Return one bounded page of terminal or expired unconsumed upload intents."""
    scan: dict[str, object] = {
        "Limit": limit,
        "FilterExpression": (
            "begins_with(PK,:upload) AND SK=:meta AND ("
            "#status IN (:invalid,:expired,:cleanup_pending) OR ("
            "#status IN (:pending,:validating,:validated,:issuing,:assembling,:promoting) "
            "AND " + PAST_USABLE + " AND " + LEASE_LAPSED + "))"
        ),
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":upload": "UPLOAD#",
            ":meta": "META",
            ":invalid": "invalid",
            ":expired": "expired",
            ":cleanup_pending": "cleanup_pending",
            ":pending": "pending_upload",
            ":validating": "validating",
            ":validated": "validated",
            ":issuing": "issuing",
            ":assembling": "assembling",
            ":promoting": "promoting",
            ":now": now_epoch,
        },
    }
    if exclusive_start_key:
        scan["ExclusiveStartKey"] = exclusive_start_key
    response = _scan(table or _table(), **scan)
    items = response.get("Items", [])
    cursor = response.get("LastEvaluatedKey")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("dependency_failure")
    if cursor is not None and (
        not isinstance(cursor, dict)
        or set(cursor) != {"PK", "SK"}
        or any(not isinstance(value, str) or not value for value in cursor.values())
    ):
        raise AttachmentRepositoryConflict("dependency_failure")
    return items, cursor


def claim_upload_cleanup(
    upload_id: str,
    version: int,
    now_epoch: int,
    reason: str,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    """Conditionally make one eligible intent non-consumable for cleanup.

    Eligible is refused or already claimed, or any other unspent state once its
    usable window is over and no operation lease is still live on it: a worker
    holding one may still have a provider write in flight, which no fence stops
    (#268).
    """
    return _apply(
        _transition_request(
            upload_id,
            version=version,
            target=UploadStatus.CLEANUP_PENDING,
            condition=(
                "#status IN (:invalid,:expired,:cleanup_pending) OR ("
                "#status IN (:pending,:validating,:validated,:issuing,:assembling,:promoting) "
                "AND " + PAST_USABLE + " AND " + LEASE_LAPSED + ")"
            ),
            values={
                ":invalid": UploadStatus.INVALID.value,
                ":expired": UploadStatus.EXPIRED.value,
                ":cleanup_pending": UploadStatus.CLEANUP_PENDING.value,
                ":pending": UploadStatus.PENDING_UPLOAD.value,
                ":validating": UploadStatus.VALIDATING.value,
                ":validated": UploadStatus.VALIDATED.value,
                ":issuing": UploadStatus.ISSUING.value,
                ":assembling": UploadStatus.ASSEMBLING.value,
                ":promoting": UploadStatus.PROMOTING.value,
                ":now": now_epoch,
            },
            attributes={"cleanup_reason": reason},
        ),
        table=table,
        return_new=True,
    )


def scan_durable_upload_references(
    upload_id: str,
    immutable_object_key: str = "",
    immutable_version_id: str = "",
    *,
    limit: int,
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[bool, dict[str, object] | None]:
    """Scan one bounded page for a durable attachment referencing upload bytes."""
    scan: dict[str, object] = {
        "Limit": limit,
        "FilterExpression": (
            "begins_with(PK,:attachment) AND SK=:meta AND "
            "(source_upload_id=:upload_id OR "
            "(immutable_object_key=:immutable_key AND immutable_version_id=:immutable_version))"
        ),
        "ExpressionAttributeValues": {
            ":attachment": "ATTACHMENT#",
            ":meta": "META",
            ":upload_id": upload_id,
            ":immutable_key": immutable_object_key,
            ":immutable_version": immutable_version_id,
        },
    }
    if exclusive_start_key:
        scan["ExclusiveStartKey"] = exclusive_start_key
    response = _scan(table or _table(), **scan)
    return bool(response.get("Items")), _optional_mapping(
        response.get("LastEvaluatedKey")
    )


def advance_upload_cleanup_reference_scan(
    upload_id: str,
    version: int,
    cursor: dict[str, object],
    *,
    table: object | None = None,
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_reference_cursor=:cursor, #version=:next",
        {":cursor": cursor, ":next": version + 1},
        table=table,
    )


def block_upload_cleanup(
    upload_id: str, version: int, *, now_epoch: int, table: object | None = None
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET #status=:blocked, #version=:next, expires_at=:retire "
        "REMOVE cleanup_reference_cursor",
        {
            ":blocked": "cleanup_blocked",
            ":next": version + 1,
            ":retire": _retire_at(now_epoch),
        },
        table=table,
    )


def complete_upload_cleanup(
    upload_id: str,
    version: int,
    cleaned_at: str,
    *,
    now_epoch: int,
    table: object | None = None,
) -> bool:
    return (
        _apply(
            _transition_request(
                upload_id,
                version=version,
                sources=(UploadStatus.CLEANUP_PENDING,),
                target=UploadStatus.CLEANUP_COMPLETE,
                condition=(
                    "cleanup_multipart_aborted=:true AND cleanup_staging_deleted=:true AND "
                    "cleanup_immutable_deleted=:true AND cleanup_parts_absent=:true"
                ),
                values={":true": True},
                attributes={"cleaned_at": cleaned_at, "expires_at": _retire_at(now_epoch)},
                remove=(
                    "staging_object_key", "staging_version_id", "staging_etag",
                    "multipart_upload_id", "immutable_object_key", "immutable_version_id",
                    "immutable_etag", "operation_kind", "operation_fence",
                    "operation_lease_expires_at", "operation_takeover_count",
                    "cleanup_reference_cursor", "cleanup_multipart_aborted",
                    "cleanup_staging_deleted", "cleanup_immutable_deleted",
                    "cleanup_multipart_cursor", "cleanup_staging_cursor",
                    "cleanup_immutable_cursor", "cleanup_multipart_mutation_attempts",
                    "cleanup_staging_mutation_attempts", "cleanup_immutable_mutation_attempts",
                    "cleanup_multipart_reconciliation_pages",
                    "cleanup_staging_reconciliation_pages",
                    "cleanup_immutable_reconciliation_pages", "cleanup_part_cursor",
                    "cleanup_parts_absent",
                ),
            ),
            table=table,
        )
        is not None
    )


def mark_cleanup_multipart_aborted(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_multipart_aborted", table=table)


def mark_cleanup_staging_deleted(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_staging_deleted", table=table)


def mark_cleanup_immutable_deleted(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_immutable_deleted", table=table)


def defer_cleanup_reconciliation(
    upload_id: str,
    version: int,
    kind: str,
    cursor: dict[str, str],
    *,
    mutation_attempted: bool,
    pages: int,
    table: object | None = None,
) -> bool:
    """Persist one bounded provider listing continuation under its cleanup generation."""
    if kind not in {"multipart", "staging", "immutable"}:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    if (
        not isinstance(cursor, dict)
        or not cursor
        or any(not isinstance(value, str) or not value.strip() for value in cursor.values())
    ):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    pages = _require_positive_integer(pages)
    mutation_increment = 1 if mutation_attempted is True else 0
    return _cleanup_update(
        upload_id,
        version,
        (
            f"SET cleanup_{kind}_cursor=:cursor, #version=:next, "
            f"cleanup_{kind}_mutation_attempts="
            f"if_not_exists(cleanup_{kind}_mutation_attempts,:zero)+:mutation, "
            f"cleanup_{kind}_reconciliation_pages="
            f"if_not_exists(cleanup_{kind}_reconciliation_pages,:zero)+:pages"
        ),
        {
            ":cursor": cursor,
            ":next": version + 1,
            ":zero": 0,
            ":mutation": mutation_increment,
            ":pages": pages,
        },
        table=table,
    )


def scrub_upload_parts(
    upload_id: str,
    version: int,
    *,
    limit: int,
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[int, dict[str, object] | None] | None:
    """Delete one bounded PART page only while the cleanup generation is current."""
    from boto3.dynamodb.conditions import Key

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 24:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    target = table or _table()
    request: dict[str, object] = {
        "KeyConditionExpression": Key("PK").eq(f"UPLOAD#{upload_id}")
        & Key("SK").begins_with("PART#"),
        "ConsistentRead": True,
        "Limit": limit,
    }
    if exclusive_start_key:
        request["ExclusiveStartKey"] = exclusive_start_key
    response = _query(target, **request)
    items = response.get("Items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("dependency_failure")
    if not items:
        return 0, None
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": upload_key(upload_id),
                "ConditionExpression": "#status=:pending AND #version=:version",
                "ExpressionAttributeNames": {"#status": "status", "#version": "version"},
                "ExpressionAttributeValues": {
                    ":pending": "cleanup_pending",
                    ":version": version,
                },
            }
        }
    ]
    for item in items:
        key = {"PK": item.get("PK"), "SK": item.get("SK")}
        if (
            key["PK"] != f"UPLOAD#{upload_id}"
            or not isinstance(key["SK"], str)
            or not key["SK"].startswith("PART#")
        ):
            raise AttachmentRepositoryConflict("dependency_failure")
        operations.append({"Delete": {"Key": key}})
    transact(operations, table=target)
    cursor = response.get("LastEvaluatedKey")
    if cursor is not None and not isinstance(cursor, dict):
        raise AttachmentRepositoryConflict("dependency_failure")
    return len(items), cursor


def advance_cleanup_part_scrub(
    upload_id: str,
    version: int,
    cursor: dict[str, object] | None,
    *,
    table: object | None = None,
) -> bool:
    if cursor is None:
        expression = "SET #version=:next REMOVE cleanup_part_cursor"
        values: dict[str, object] = {":next": version + 1}
    elif isinstance(cursor, dict) and cursor:
        expression = "SET cleanup_part_cursor=:cursor, #version=:next"
        values = {":cursor": cursor, ":next": version + 1}
    else:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return _cleanup_update(upload_id, version, expression, values, table=table)


def mark_cleanup_parts_absent(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_parts_absent=:true, #version=:next REMOVE cleanup_part_cursor",
        {":true": True, ":next": version + 1},
        table=table,
    )


def record_cleanup_staging_version(
    upload_id: str, version: int, version_id: str, etag: str, *, table: object | None = None
) -> bool:
    version_id = _require_provider_coordinate(version_id)
    etag = _require_provider_coordinate(etag)
    return _cleanup_update(
        upload_id,
        version,
        "SET staging_version_id=:target, staging_etag=:etag, #version=:next",
        {":target": version_id, ":etag": etag, ":next": version + 1},
        table=table,
    )


def record_cleanup_immutable_version(
    upload_id: str, version: int, version_id: str, etag: str, *, table: object | None = None
) -> bool:
    version_id = _require_provider_coordinate(version_id)
    etag = _require_provider_coordinate(etag)
    return _cleanup_update(
        upload_id,
        version,
        "SET immutable_version_id=:target, immutable_etag=:etag, #version=:next",
        {":target": version_id, ":etag": etag, ":next": version + 1},
        table=table,
    )


def _cleanup_progress(
    upload_id: str, version: int, field: str, *, table: object | None
) -> bool:
    kind = {
        "cleanup_multipart_aborted": "multipart",
        "cleanup_staging_deleted": "staging",
        "cleanup_immutable_deleted": "immutable",
    }[field]
    return _cleanup_update(
        upload_id,
        version,
        (
            f"SET {field}=:true, #version=:next "
            f"REMOVE cleanup_{kind}_cursor"
        ),
        {":true": True, ":next": version + 1},
        table=table,
    )


def _cleanup_update(
    upload_id: str,
    version: int,
    update_expression: str,
    values: dict[str, object],
    *,
    table: object | None,
) -> bool:
    try:
        _update_item(table or _table(),
            Key=upload_key(upload_id),
            UpdateExpression=update_expression,
            ConditionExpression="#status=:pending AND #version=:version",
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                **values,
                ":pending": "cleanup_pending",
                ":version": version,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def claim_account_upload_cleanup(
    upload: dict[str, object],
    *,
    owner_id: str,
    account_fence_generation: int,
    table: object | None = None,
) -> dict[str, object] | None:
    """Make any account-owned upload non-consumable under the account fence."""
    upload_id = _required_text(upload.get("upload_id"))
    upload_version = _required_integer(upload.get("version"), minimum=1)
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(owner_id),
                "ConditionExpression": "#status=:pending AND generation=:generation",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":pending": "deletion_pending",
                    ":generation": account_fence_generation,
                },
            }
        },
        {
            "Update": _transition_request(
                upload_id,
                version=upload_version,
                owner_id=owner_id,
                target=UploadStatus.CLEANUP_PENDING,
                condition="#status<>:complete",
                values={":complete": UploadStatus.CLEANUP_COMPLETE.value},
                attributes={"cleanup_reason": "account_closure"},
                remove=("durable_attachment_id",),
            )
        },
    ]
    try:
        transact(operations, table=table)
    except AttachmentRepositoryConflict:
        return None
    current = get_upload_intent(upload_id, table=table)
    if (
        not current
        or current.get("owner_id") != owner_id
        or current.get("status") != "cleanup_pending"
    ):
        return None
    return current


def delete_account_upload_tombstone(
    upload_id: str,
    *,
    owner_id: str,
    account_fence_generation: int,
    table: object | None = None,
) -> bool:
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(owner_id),
                "ConditionExpression": "#status=:pending AND generation=:generation",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":pending": "deletion_pending",
                    ":generation": account_fence_generation,
                },
            }
        },
        {
            "Delete": {
                "Key": upload_key(upload_id),
                "ConditionExpression": "owner_id=:owner AND #status=:complete",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": owner_id,
                    ":complete": "cleanup_complete",
                },
            }
        },
    ]
    try:
        transact(operations, table=table)
    except AttachmentRepositoryConflict:
        return False
    return True


def begin_immutable_promotion(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    operation_fence: str,
    immutable_object_key: str,
    content_sha256: str,
    content_length: int,
    detected_type: str,
    image_width: int | None,
    image_height: int | None,
    table: object | None = None,
) -> bool:
    """Fence and persist the exact immutable target before PutObject."""
    operation_fence = _require_provider_coordinate(operation_fence)
    immutable_object_key = _require_provider_coordinate(immutable_object_key)
    content_sha256 = _require_canonical_sha256(content_sha256)
    content_length = _require_positive_integer(content_length)
    detected_type = _require_provider_coordinate(detected_type)
    return _transition(
        upload_id,
        owner_id,
        "validating",
        "promoting",
        version,
        now_epoch,
        attributes={
            "operation_kind": "immutable_promotion",
            "operation_fence": operation_fence,
            "operation_lease_expires_at": now_epoch + 120,
            "operation_takeover_count": 0,
            "immutable_object_key": immutable_object_key,
            "content_sha256": content_sha256,
            "content_length": content_length,
            "detected_type": detected_type,
            "image_width": image_width,
            "image_height": image_height,
        },
        table=table,
    )


def record_immutable_version(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    immutable_version_id: object,
    immutable_etag: object,
    validated_at: str,
    table: object | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    immutable_version_id = _require_provider_coordinate(immutable_version_id)
    immutable_etag = _require_provider_coordinate(immutable_etag)
    return _fenced_transition(
        upload_id,
        owner_id,
        "promoting",
        "validated",
        version,
        operation_fence,
        attributes={
            "immutable_version_id": immutable_version_id,
            "immutable_etag": immutable_etag,
            "validated_at": validated_at,
            "staging_cleanup_status": "pending",
        },
        remove_operation=True,
        table=table,
    )


def clear_staging_coordinates(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    table: object | None = None,
) -> bool:
    """Forget a promoted upload's staging copy, once it is proven gone."""
    return (
        _apply(
            _transition_request(
                upload_id,
                version=version,
                owner_id=owner_id,
                sources=(UploadStatus.VALIDATED,),
                target=UploadStatus.VALIDATED,
                remove=(
                    "staging_object_key", "staging_version_id", "staging_etag",
                    "multipart_upload_id", "staging_cleanup_status",
                ),
            ),
            table=table,
        )
        is not None
    )


def mark_invalid(
    upload_id: str, owner_id: str, version: int, failure_category: str, *, table: object | None = None
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "validating",
        "invalid",
        version,
        None,
        attributes={"validation_failure": failure_category},
        table=table,
    )


# An upload's usable window (#250). The table's TTL attribute is `expires_at`,
# so a row written before `usable_until` existed carries its window there.
USABLE = "(usable_until > :now OR (attribute_not_exists(usable_until) AND expires_at > :now))"


PAST_USABLE = (
    "(usable_until <= :now OR (attribute_not_exists(usable_until) AND expires_at <= :now))"
)
# No operation is under way on the row: none was leased, or its lease has run out.
LEASE_LAPSED = (
    "(attribute_not_exists(operation_lease_expires_at) OR operation_lease_expires_at <= :now)"
)


def usable_until(item: Mapping[str, object]) -> int:
    """Until when an upload may still be used, as the epoch second it ends."""
    stored = item.get("usable_until")
    if stored is None:
        stored = item.get("expires_at", 0)
    return _required_integer(stored)


def _retire_at(now_epoch: int) -> int:
    """When an upload row that ends at `now_epoch` leaves the table, by its TTL."""
    return now_epoch + UPLOAD_ROW_RETENTION_SECONDS


def _transition_request(
    upload_id: str,
    *,
    version: int,
    target: str,
    sources: Sequence[str] = (),
    owner_id: str | None = None,
    operation_fence: str | None = None,
    usable_at: int | None = None,
    condition: str | None = None,
    values: Mapping[str, object] | None = None,
    attributes: Mapping[str, object] | None = None,
    remove: Sequence[str] = (),
) -> dict[str, object]:
    """The conditional update that moves one upload row to `target`, as a request.

    Every state change of an upload row is one of these. It holds on the version
    (and moves it one on), and as asked on the owner, the source states, the
    operation fence, the usable window at `usable_at`, and a further `condition`
    over its own `values`. `attributes` are set and `remove` removed with it.
    """
    names: dict[str, str] = {"#status": "status", "#version": "version"}
    expression_values: dict[str, object] = {
        ":target": str(target),
        ":version": version,
        ":next": version + 1,
    }
    conditions: list[str] = []
    if owner_id is not None:
        names["#owner"] = "owner_id"
        expression_values[":owner"] = owner_id
        conditions.append("#owner=:owner")
    if sources:
        placeholders = [f":source{index}" for index in range(len(sources))]
        expression_values.update(zip(placeholders, (str(source) for source in sources)))
        conditions.append(
            "#status=" + placeholders[0]
            if len(placeholders) == 1
            else "#status IN (" + ",".join(placeholders) + ")"
        )
    conditions.append("#version=:version")
    if operation_fence is not None:
        names["#fence"] = "operation_fence"
        expression_values[":fence"] = operation_fence
        conditions.append("#fence=:fence")
    if usable_at is not None:
        expression_values[":now"] = usable_at
        conditions.append(USABLE)
    if condition is not None:
        conditions.append("(" + condition + ")")
    expression_values.update(values or {})
    update = "SET #status=:target, #version=:next"
    for index, (name, value) in enumerate((attributes or {}).items()):
        names[f"#a{index}"] = name
        expression_values[f":a{index}"] = value
        update += f", #a{index}=:a{index}"
    if remove:
        update += " REMOVE " + ", ".join(remove)
    return {
        "Key": upload_key(upload_id),
        "UpdateExpression": update,
        "ConditionExpression": " AND ".join(conditions),
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": expression_values,
    }


def _apply(
    request: dict[str, object], *, table: object | None, return_new: bool = False
) -> dict[str, object] | None:
    """Make one transition; the row as it now is (or `{}`), `None` when its condition failed."""
    try:
        response = _update_item(
            table or _table(),
            **request,
            **({"ReturnValues": "ALL_NEW"} if return_new else {}),
        )
    except ClientError as exc:
        if _conditional(exc):
            return None
        raise AttachmentRepositoryConflict("dependency_failure") from None
    if not return_new:
        return {}
    return _optional_mapping(response.get("Attributes"))


def _transition(
    upload_id: str,
    owner_id: str,
    source: str,
    target: str,
    version: int,
    now_epoch: int | None,
    *,
    attributes: dict[str, object] | None = None,
    table: object | None = None,
) -> bool:
    return (
        _apply(
            _transition_request(
                upload_id,
                version=version,
                target=target,
                sources=(source,),
                owner_id=owner_id,
                usable_at=now_epoch,
                attributes=attributes,
            ),
            table=table,
        )
        is not None
    )


def _fenced_transition(
    upload_id: str,
    owner_id: str,
    source: str,
    target: str,
    version: int,
    operation_fence: str,
    *,
    attributes: dict[str, object] | None = None,
    remove_operation: bool = False,
    table: object | None = None,
) -> bool:
    return (
        _apply(
            _transition_request(
                upload_id,
                version=version,
                target=target,
                sources=(source,),
                owner_id=owner_id,
                operation_fence=operation_fence,
                attributes=attributes,
                remove=(
                    (
                        "operation_kind",
                        "operation_fence",
                        "operation_lease_expires_at",
                        "operation_takeover_count",
                    )
                    if remove_operation
                    else ()
                ),
            ),
            table=table,
        )
        is not None
    )


def consume_operation(
    upload: Mapping[str, object],
    *,
    attachment_id: str,
    now_epoch: int,
    owner_id: str,
    new_owner_id: str | None = None,
    account_fence_generation: int | None = None,
) -> dict[str, object]:
    """The update that spends a validated upload on the attachment it becomes.

    It belongs in the caller's transaction, next to that attachment's put: the
    upload is spent only if the message or reply that carries it is written.
    With `new_owner_id` the upload changes hands as it is spent (a teacher's
    reply image becomes the student's, #145), and `account_fence_generation`
    is the new owner's.
    """
    attributes: dict[str, object] = {
        "durable_attachment_id": attachment_id,
        "expires_at": now_epoch + UPLOAD_ROW_RETENTION_SECONDS,
    }
    if new_owner_id is not None:
        attributes.update(
            owner_id=new_owner_id,
            student_id=new_owner_id,
            account_fence_generation=account_fence_generation,
        )
    return {
        "Update": _transition_request(
            _required_text(upload.get("upload_id")),
            version=_required_integer(upload.get("version"), minimum=1),
            owner_id=owner_id,
            sources=(UploadStatus.VALIDATED,),
            target=UploadStatus.CONSUMED,
            usable_at=now_epoch,
            attributes=attributes,
        )
    }


def list_owner_staging_cleanup_debts(
    owner_id: str, *, table: object | None = None
) -> list[dict[str, object]]:
    return [
        item
        for item in list_owner_attachment_items(
            owner_id,
            table=table,
            entity_types=None,
        )
        if item.get("staging_cleanup_status") == "pending"
    ]
