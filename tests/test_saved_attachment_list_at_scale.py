"""The saved attachment list answers from the owner's rows, not the whole table (#136).

`GET /files/attachments` read the shared single table with a consistent scan of at
most 100 pages of 100 rows and gave up past that. Production holds far more than
10,000 rows - every message, usage event and upload of every account - so the list
answered 503 for everyone.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor
from stoa.routers import files
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from fakes.dynamodb import FakeTable


OWNER = "student-owner"


def _actor(user_id: str = OWNER) -> Actor:
    return Actor(
        user_id, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student"
    )


def _attachment(attachment_id: str, *, owner_id: str = OWNER, status: str = "active") -> dict[str, Any]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": "META",
        "entity_type": "attachment",
        "schema_version": "attachment.v1",
        "attachment_id": attachment_id,
        "owner_id": owner_id,
        "student_id": owner_id,
        "status": status,
        "ref_count": 0,
        "original_filename": f"{attachment_id}.png",
        "detected_type": "image/png",
        "content_length": 1024,
        "content_sha256": "a" * 64,
        "immutable_object_key": f"objects/{attachment_id}",
        "immutable_version_id": "version-1",
        "immutable_etag": "etag-1",
        "created_at": f"2026-10-0{attachment_id[-1]}T08:00:00+00:00",
    }


def _message(student_id: str, index: int) -> dict[str, Any]:
    return {
        "PK": f"CONVERSATION#{student_id}-c",
        "SK": f"MSG#{index:06d}",
        "entity_type": "message",
        "student_id": student_id,
        "content": "x" * 40,
        "created_at": f"2026-10-01T{index // 3600 % 24:02d}:{index // 60 % 60:02d}:{index % 60:02d}+00:00",
    }


def _busy_table(other_rows: int, *, page_item_cap: int | None = None) -> FakeTable:
    """The owner's files among other accounts' rows, as the shared table holds them.

    The owner's messages sort ahead of their files in the index, so with a small
    `page_item_cap` the files only turn up a few pages in.
    """
    table = FakeTable(page_item_cap=page_item_cap)
    table.seed(
        _attachment("owned-3"),
        _attachment("owned-1"),
        _attachment("owned-2"),
        _attachment("owned-9", status="deletion_pending"),
        _attachment("foreign-1", owner_id="student-other"),
        {
            "PK": "UPLOAD#upload-1",
            "SK": "META",
            "entity_type": "upload_intent",
            "upload_id": "upload-1",
            "owner_id": OWNER,
            "student_id": OWNER,
            "status": "validated",
            "created_at": "2026-10-05T08:00:00+00:00",
        },
        *(_message(OWNER, index) for index in range(30)),
    )
    for index in range(other_rows):
        table.seed(_message(f"student-{index % 400}", index))
    return table


def _client(monkeypatch: pytest.MonkeyPatch, table: FakeTable) -> TestClient:
    monkeypatch.setattr(attachment_repo, "get_table", lambda: table)
    app = FastAPI()
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_actor] = _actor
    return TestClient(app)


def _listed(client: TestClient, **params: Any) -> list[str]:
    seen: list[str] = []
    continuation = None
    for _ in range(10):
        query = dict(params)
        if continuation:
            query["continuation"] = continuation
        response = client.get("/files/attachments", params=query)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(item["attachmentId"] for item in body["items"])
        continuation = body["continuation"]
        if not continuation:
            return seen
    raise AssertionError("the list never ended")


def test_list_answers_on_a_table_larger_than_ten_thousand_rows(monkeypatch) -> None:
    client = _client(monkeypatch, _busy_table(other_rows=10_050))

    assert _listed(client) == ["owned-1", "owned-2", "owned-3"]


def test_list_pages_through_the_owner_files_only(monkeypatch) -> None:
    client = _client(monkeypatch, _busy_table(other_rows=200, page_item_cap=7))

    assert _listed(client, limit=1) == ["owned-1", "owned-2", "owned-3"]
    assert _listed(client, limit=2) == ["owned-1", "owned-2", "owned-3"]


class _ReadCountingTable(FakeTable):
    def __init__(self) -> None:
        super().__init__()
        self.rows_read = 0

    def _page(self, candidates, kwargs, *, sort_key):
        response = super()._page(candidates, kwargs, sort_key=sort_key)
        self.rows_read += response["ScannedCount"]
        return response


def test_list_reads_the_owner_rows_rather_than_the_table(monkeypatch) -> None:
    table = _ReadCountingTable()
    table.rows = _busy_table(other_rows=3_000).rows
    client = _client(monkeypatch, table)

    assert _listed(client) == ["owned-1", "owned-2", "owned-3"]
    # The owner holds 36 rows; the table holds over 3,000.
    assert table.rows_read <= 36
