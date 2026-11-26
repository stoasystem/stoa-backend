"""GSI-Listing reads that wait for their backfill (card 135).

A list moved onto GSI-Listing holds only the rows written by a release that
sets `listing` and `listed_at`; the rows written before join it when
`scripts/backfill_listing_index_admin.py --apply` writes their keys. Until that
run has finished, the list's reader keeps its old scan: the backfill writes one
marker row per list as its last step, and a reader asks for it first.
"""

from __future__ import annotations

from stoa.db import table as db_table

INDEX = "GSI-Listing"
INDEX_KEY = ("PK", "SK", "listing", "listed_at")
MARKER_PK = "LISTING_BACKFILL"


def marker_key(listing: str) -> dict[str, str]:
    return {"PK": MARKER_PK, "SK": f"LISTING#{listing}"}


def backfilled(listing: str, *, table: object | None = None) -> bool:
    """Whether the backfill of `listing` has finished, so the index holds every row."""
    item = db_table.get(table=table, Key=marker_key(listing), ConsistentRead=True)
    return item is not None and item.get("complete") is True
