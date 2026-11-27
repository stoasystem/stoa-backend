"""The student curriculum, stored compressed under its catalog stamp (#669).

`curriculum_cache` keeps the student curriculum per Lambda container. A
container without it paged the whole `PRACTICE` partition - two thousand
lessons, some two seconds - and a page load spreads its requests over several
containers, so with few students nearly every load met one such container.
Now the first container to page the partition under a stamp stores what it
read here, and every other container loads that with one `GetItem` (and one
`BatchGetItem` when it does not fit in one item).

- **Keyed by the stamp.** The head row is `PRACTICE_CATALOG` /
  `SNAPSHOT#<stamp>`; a container asks only for the stamp it has just read, so
  a snapshot taken under another stamp is never used.
- **Written once, whole.** The rows are encoded (`Decimal`, sets and binary
  values come back as they went in), gzip-compressed and cut into parts of at
  most `PART_BYTES`. The parts after the first are written first, under a write
  id of their own; the head - the first part, the number of parts and the
  SHA-256 of the whole - last, on the condition that no other head took its
  place in the meantime. Two containers that page at once do not mix their
  parts: the one whose head lands is read, the other's parts expire.
- **Checked when read.** A head of another format, a missing part or a digest
  that does not match is not used: the reader pages the partition, as before,
  and replaces that head.
- **Bounded in age.** A head older than `MAX_AGE` is not used either, and is
  replaced. That is the bound for a writer that changes the curriculum without
  writing a new stamp; every writer in `src` and `scripts` writes one. Every row
  carries `expires_at`, the table's TTL attribute, so the rows of old stamps go
  away on their own.
- **Taken from settled rows.** The partition is read with eventually consistent
  queries, so a snapshot is stored only when the stamp was written at least
  `SETTLE` seconds before the read began; otherwise rows a publish had just
  written might be missing from what is stored for every container.

Nothing here fails a request: a load that cannot be made says so and the
caller reads the partition; a store that cannot be made is logged.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import math
import uuid
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from boto3.dynamodb.types import Binary

from stoa.db import table as db_table

PK = "PRACTICE_CATALOG"
ENTITY = "curriculum_catalog_snapshot"
FORMAT = 1
#: The compressed bytes one row holds; DynamoDB's item limit is 400 KB.
PART_BYTES = 350_000
#: More parts than this is not stored: it would no longer be one cheap read.
MAX_PARTS = 32
#: What the compressed rows may expand to when they are read back.
MAX_RAW_BYTES = 256 * 1024 * 1024
MAX_AGE = 24 * 60 * 60
#: How long after it was written a row of an old stamp is left for the TTL to remove.
EXPIRY_MARGIN = 60 * 60
SETTLE = 10.0

ROW_KINDS = ("subjects", "topics", "units", "lessons")

logger = logging.getLogger(__name__)

type Rows = dict[str, Any]


class Unstorable(ValueError):
    """The rows hold a value this encoding does not carry."""


class Broken(ValueError):
    """What was stored cannot be read back as rows."""


@dataclass(frozen=True)
class Loaded:
    """What a load found.

    `rows`: the stored rows, when they can be used. `head`: the write id of a
    head that was found and not used, which a store replaces. `storable`:
    whether storing may be tried at all - not when the table could not be asked.
    """

    rows: Rows | None
    head: str | None = None
    storable: bool = True


def head_key(stamp: str) -> dict[str, str]:
    return {"PK": PK, "SK": f"SNAPSHOT#{stamp}"}


def part_key(stamp: str, write_id: str, part: int) -> dict[str, str]:
    return {"PK": PK, "SK": f"SNAPSHOT#{stamp}#{write_id}#{part:03d}"}


# -- loading ------------------------------------------------------------------------------


def load(stamp: str, *, table: object, now: float) -> Loaded:
    """The rows stored under `stamp`, or why not."""
    try:
        head = db_table.get(table=table, Key=head_key(stamp))
    except Exception:  # noqa: BLE001 - the caller reads the partition instead
        logger.warning("curriculum_snapshot_unusable reason=head_unreadable", exc_info=True)
        return Loaded(None, storable=False)
    if head is None:
        logger.info("curriculum_snapshot_unusable reason=absent")
        return Loaded(None)
    write_id = str(head.get("write_id") or "")
    try:
        rows, size, parts = _rows_of(stamp, head, table=table, now=now)
    except Broken as reason:
        logger.info("curriculum_snapshot_unusable reason=%s", reason)
        return Loaded(None, head=write_id)
    except Exception:  # noqa: BLE001 - a part that could not be read is a missing part
        logger.warning("curriculum_snapshot_unusable reason=parts_unreadable", exc_info=True)
        return Loaded(None, head=write_id)
    logger.info("curriculum_snapshot_loaded parts=%d bytes=%d", parts, size)
    return Loaded(rows)


def _rows_of(stamp: str, head: Mapping[str, Any], *, table: object, now: float) -> tuple[Rows, int, int]:
    if _number(head.get("format")) != FORMAT:
        raise Broken("format")
    written_at = _number(head.get("written_at"))
    if written_at is None or now - written_at >= MAX_AGE:
        raise Broken("too_old")
    write_id = head.get("write_id")
    parts = _number(head.get("parts"))
    if not isinstance(write_id, str) or not write_id or parts is None or not 1 <= parts <= MAX_PARTS:
        raise Broken("head")
    chunks = [_bytes(head.get("data"))]
    if parts > 1:
        keys = [part_key(stamp, write_id, part) for part in range(1, int(parts))]
        found = db_table.get_many(keys, table=table)
        for key in keys:
            row = found.get((key["PK"], key["SK"]))
            if row is None or row.get("write_id") != write_id:
                raise Broken("part_missing")
            chunks.append(_bytes(row.get("data")))
    blob = b"".join(chunks)
    if hashlib.sha256(blob).hexdigest() != head.get("digest"):
        raise Broken("digest")
    return decode(blob), len(blob), int(parts)


def _number(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        return None
    if isinstance(value, Decimal) and value != value.to_integral_value():
        return None
    return int(value)


def _bytes(value: object) -> bytes:
    if isinstance(value, Binary):
        return _binary(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise Broken("data")


def _binary(value: object) -> bytes:
    # boto3's `Binary` wraps the bytes in `.value`, which its stubs do not declare.
    return bytes(getattr(value, "value"))


# -- storing ------------------------------------------------------------------------------


def store(stamp: str, rows: Rows, *, replacing: str | None, table: object, now: float) -> bool:
    """Store `rows` under `stamp`; whether this write's head landed.

    `replacing` is the write id of the head `load` found and did not use; with
    none, only an absent head is replaced.
    """
    try:
        blob = encode(rows)
    except Unstorable as reason:
        logger.warning("curriculum_snapshot_not_stored reason=%s", reason)
        return False
    except Exception:  # noqa: BLE001 - the request that read the rows must not fail
        logger.warning("curriculum_snapshot_not_stored reason=encode_failed", exc_info=True)
        return False
    chunks = [blob[start : start + PART_BYTES] for start in range(0, len(blob), PART_BYTES)]
    if len(chunks) > MAX_PARTS:
        logger.warning(
            "curriculum_snapshot_not_stored reason=too_large bytes=%d parts=%d",
            len(blob),
            len(chunks),
        )
        return False
    write_id = uuid.uuid4().hex
    written_at = math.floor(now)
    expires_at = written_at + MAX_AGE + EXPIRY_MARGIN
    try:
        _put_snapshot(stamp, write_id, chunks, blob, replacing, written_at, expires_at, table)
    except db_table.WriteRefused as refused:
        if refused.condition_failed:
            # Another container stored it first; its head is the one read.
            logger.info("curriculum_snapshot_not_stored reason=stored_by_another")
        else:
            logger.warning("curriculum_snapshot_not_stored reason=refused", exc_info=True)
        return False
    except Exception:  # noqa: BLE001 - the request that read the rows must not fail
        logger.warning("curriculum_snapshot_not_stored reason=write_failed", exc_info=True)
        return False
    logger.info("curriculum_snapshot_stored parts=%d bytes=%d", len(chunks), len(blob))
    return True


def _put_snapshot(
    stamp: str,
    write_id: str,
    chunks: list[bytes],
    blob: bytes,
    replacing: str | None,
    written_at: int,
    expires_at: int,
    table: object,
) -> None:
    """The parts after the first, then the head on its condition.

    Curriculum content names no account, so no deletion acts on these rows and
    nothing is registered for them.
    """
    for part, chunk in enumerate(chunks[1:], start=1):
        db_table.put(
            table=table,
            Item={
                **part_key(stamp, write_id, part),
                "entity_type": ENTITY,
                "write_id": write_id,
                "part": part,
                "data": chunk,
                "expires_at": expires_at,
            },
        )
    condition: dict[str, object] = {"ConditionExpression": "attribute_not_exists(PK)"}
    if replacing is not None:
        condition = {
            "ConditionExpression": "attribute_not_exists(PK) OR write_id = :replacing",
            "ExpressionAttributeValues": {":replacing": replacing},
        }
    db_table.put(
        table=table,
        Item={
            **head_key(stamp),
            "entity_type": ENTITY,
            "format": FORMAT,
            "stamp": stamp,
            "write_id": write_id,
            "parts": len(chunks),
            "digest": hashlib.sha256(blob).hexdigest(),
            "data": chunks[0],
            "written_at": written_at,
            "expires_at": expires_at,
        },
        **condition,
    )


# -- the encoding -------------------------------------------------------------------------

# A map with one key that starts with NUL stands for a value JSON has no form for.
_TAG = "\u0000"


def encode(rows: Rows) -> bytes:
    """`rows` as gzip-compressed JSON; `Unstorable` when a value has no form here."""
    payload: dict[str, Any] = {kind: [_encoded(row) for row in rows[kind]] for kind in ROW_KINDS}
    challenges = rows["challenges"]
    if not isinstance(challenges, Mapping):
        raise Unstorable("challenges")
    encoded_challenges: dict[str, Any] = {}
    for lesson_id, found in challenges.items():
        if not isinstance(found, list):
            raise Unstorable("unread_challenges")
        encoded_challenges[str(lesson_id)] = [_encoded(row) for row in found]
    payload["challenges"] = encoded_challenges
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0)


def decode(blob: bytes) -> Rows:
    """What `encode` was given; `Broken` when `blob` is not something it wrote."""
    try:
        inflater = zlib.decompressobj(wbits=31)
        raw = inflater.decompress(blob, MAX_RAW_BYTES)
        if inflater.unconsumed_tail or not inflater.eof:
            raise Broken("truncated")
        payload = json.loads(raw.decode("utf-8"), object_hook=_decoded)
    except Broken:
        raise
    except (zlib.error, InvalidOperation, ValueError, TypeError) as error:
        raise Broken("undecodable") from error
    if not isinstance(payload, dict):
        raise Broken("shape")
    rows: Rows = {}
    for kind in ROW_KINDS:
        found = payload.get(kind)
        if not isinstance(found, list) or not all(isinstance(row, dict) for row in found):
            raise Broken("shape")
        rows[kind] = found
    challenges = payload.get("challenges")
    if not isinstance(challenges, dict) or not all(
        isinstance(found, list) and all(isinstance(row, dict) for row in found)
        for found in challenges.values()
    ):
        raise Broken("shape")
    rows["challenges"] = challenges
    return rows


def _encoded(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Unstorable("float")
        return value
    if isinstance(value, Decimal):
        return {_TAG + "n": str(value)}
    if isinstance(value, Binary):
        return {_TAG + "B": base64.b64encode(_binary(value)).decode("ascii")}
    if isinstance(value, (bytes, bytearray)):
        return {_TAG + "b": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (set, frozenset)):
        return {_TAG + "s": [_encoded(member) for member in value]}
    if isinstance(value, (list, tuple)):
        return [_encoded(member) for member in value]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for name, member in value.items():
            if not isinstance(name, str) or name.startswith(_TAG):
                raise Unstorable("name")
            out[name] = _encoded(member)
        return out
    raise Unstorable(type(value).__name__)


def _decoded(found: dict[str, Any]) -> Any:
    if len(found) != 1:
        return found
    ((name, value),) = found.items()
    if not name.startswith(_TAG):
        return found
    kind = name[len(_TAG) :]
    if kind == "n" and isinstance(value, str):
        return Decimal(value)
    if kind == "b" and isinstance(value, str):
        return base64.b64decode(value, validate=True)
    if kind == "B" and isinstance(value, str):
        return Binary(base64.b64decode(value, validate=True))
    if kind == "s" and isinstance(value, list):
        return set(value)
    raise Broken("tag")
