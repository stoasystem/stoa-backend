"""Where an upload is, as anyone outside the upload package may know it (#252).

Inside the package an upload row has eleven states; outside it has four phases.
Ready is validated within its usable window, or already spent on a message;
expired is the window over before it was spent, whatever state it was left in;
failed is refused or handed to cleanup; the rest is in progress. The phone code
screen used to call a validated upload past its window "ready" although no
message could take it any more.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from stoa.db import table as db_table
from stoa.models.attachment import UploadStatus
from stoa.services import uploads
from stoa.services.uploads import _store as upload_store
from fakes.dynamodb import FakeTable

NOW = 1_800_000_000
OWNER = "student-1"


def _row(status: str, *, usable_until: int = NOW + 60, **extra: object) -> dict[str, object]:
    return {"upload_id": "upload-1", "owner_id": OWNER, "status": status, "usable_until": usable_until, **extra}


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (UploadStatus.ISSUING, uploads.Phase.IN_PROGRESS),
        (UploadStatus.PENDING_UPLOAD, uploads.Phase.IN_PROGRESS),
        (UploadStatus.ASSEMBLING, uploads.Phase.IN_PROGRESS),
        (UploadStatus.VALIDATING, uploads.Phase.IN_PROGRESS),
        (UploadStatus.PROMOTING, uploads.Phase.IN_PROGRESS),
        (UploadStatus.VALIDATED, uploads.Phase.READY),
        (UploadStatus.CONSUMED, uploads.Phase.READY),
        (UploadStatus.INVALID, uploads.Phase.FAILED),
        (UploadStatus.CLEANUP_PENDING, uploads.Phase.FAILED),
        (UploadStatus.CLEANUP_BLOCKED, uploads.Phase.FAILED),
        (UploadStatus.CLEANUP_COMPLETE, uploads.Phase.FAILED),
    ],
)
def test_every_stored_state_is_one_of_four_phases_within_the_window(state, expected) -> None:
    assert uploads.phase(_row(state), NOW) is expected


@pytest.mark.parametrize("state", [UploadStatus.VALIDATED, UploadStatus.PENDING_UPLOAD, UploadStatus.PROMOTING])
def test_an_unspent_upload_past_its_window_is_expired(state) -> None:
    assert uploads.phase(_row(state, usable_until=NOW), NOW) is uploads.Phase.EXPIRED


def test_a_spent_upload_stays_ready_after_its_window() -> None:
    """It went into a message; the phone that sent it is done."""
    assert uploads.phase(_row(UploadStatus.CONSUMED, usable_until=NOW - 1), NOW) is uploads.Phase.READY


def test_an_old_row_without_a_usable_window_reads_it_from_the_ttl_field() -> None:
    row = _row(UploadStatus.VALIDATED, expires_at=NOW)
    row.pop("usable_until")
    assert uploads.phase(row, NOW) is uploads.Phase.EXPIRED


def test_status_reads_the_owners_row_and_nobody_elses(monkeypatch) -> None:
    table = FakeTable()
    table.seed({**upload_store.upload_key("upload-1"), **_row(UploadStatus.VALIDATED)})
    db_table.install(table)
    at = datetime.fromtimestamp(NOW, UTC)

    assert uploads.status("upload-1", OWNER, now=at) is uploads.Phase.READY
    assert uploads.status("upload-1", "student-2", now=at) is None
    assert uploads.status("upload-missing", OWNER, now=at) is None
