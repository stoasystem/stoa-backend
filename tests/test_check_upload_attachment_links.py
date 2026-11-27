"""The read-only comparison run before upload cleanup trusts `durable_attachment_id` (#654)."""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import check_upload_attachment_links as links


def _attachment(table: FakeTable, attachment_id: str, source: str | None, obj: str) -> None:
    row: dict[str, Any] = {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": "META",
        "attachment_id": attachment_id,
        "owner_id": "student-private-canary",
        "original_filename": "private-name-canary.pdf",
        "status": "active",
        "immutable_object_key": f"objects/{obj}",
        "immutable_version_id": "v1",
    }
    if source is not None:
        row["source_upload_id"] = source
    table.seed(row)


def _upload(table: FakeTable, upload_id: str, obj: str | None, names: str | None, status: str) -> None:
    row: dict[str, Any] = {
        "PK": f"UPLOAD#{upload_id}",
        "SK": "META",
        "upload_id": upload_id,
        "owner_id": "student-private-canary",
        "status": status,
    }
    if obj is not None:
        row.update(immutable_object_key=f"objects/{obj}", immutable_version_id="v1")
    if names is not None:
        row["durable_attachment_id"] = names
    table.seed(row)


@pytest.fixture
def table() -> FakeTable:
    return FakeTable()


def test_attachments_their_uploads_name_are_safe_and_the_run_writes_nothing(table, capsys):
    _attachment(table, "a1", "u1", "o1")
    _upload(table, "u1", "o1", "a1", "consumed")
    _attachment(table, "a2", "u2", "o2")  # its upload has left by TTL
    _upload(table, "u3", None, None, "invalid")  # an upload never spent
    before = {key: dict(row) for key, row in table.rows.items()}

    assert links.run(table) == 0

    out = capsys.readouterr().out
    assert "named: 1" in out
    assert "upload gone: 1" in out
    assert "To explain before upload cleanup trusts durable_attachment_id: 0" in out
    assert table.rows == before
    assert table.calls["scan"] >= 1
    assert not {"put_item", "update_item", "delete_item", "transact_write_items"} & set(
        name for name, count in table.calls.items() if count
    )


def test_every_attachment_its_upload_does_not_name_is_listed(table, capsys):
    _attachment(table, "a1", "u1", "o1")
    _upload(table, "u1", "o1", None, "cleanup_pending")
    _attachment(table, "a2", "u2", "o2")
    _upload(table, "u2", "o2", "a-other", "consumed")
    _attachment(table, "a3", "u3", "o3")
    _upload(table, "u3", "o3", "a3", "consumed")
    _upload(table, "u4", "o3", None, "invalid")  # another upload holds a3's object
    _attachment(table, "a5", None, "o5")

    assert links.run(table) == 1

    out = capsys.readouterr().out
    assert "upload names none: attachment a1 (active), upload u1 (cleanup_pending)" in out
    assert "upload names another: attachment a2 (active), upload u2 (consumed)" in out
    assert "shared object: attachment a3 (active), upload u4 (invalid)" in out
    assert "no source upload: attachment a5 (active), upload - (-)" in out
    assert "To explain before upload cleanup trusts durable_attachment_id: 4" in out
    assert "private-name-canary" not in out
    assert "student-private-canary" not in out
    assert "objects/" not in out


class _SmallPages(FakeTable):
    """The shared table, answering a Scan seven rows at a time."""

    def scan(self, **request: Any) -> dict[str, Any]:
        return super().scan(**{**request, "Limit": 7})


def test_every_page_of_the_scan_is_read():
    table = _SmallPages()
    for index in range(30):
        _attachment(table, f"a{index}", f"u{index}", f"o{index}")
        _upload(table, f"u{index}", f"o{index}", f"a{index}", "consumed")

    report = links.check(links.meta_rows(table))

    assert report.counts["named"] == 30
    assert table.calls["scan"] > 1
