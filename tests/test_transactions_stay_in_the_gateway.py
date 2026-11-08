"""A transaction reaches DynamoDB through the table gateway and nowhere else (#296).

Four writers once sent `transact_write_items` themselves, each with its own
serializer and its own idea of which `None` to leave out, and three repository
specific hooks let the test doubles skip the real path. `stoa.db.table.transact`
is the one entry now; a file below `src/stoa` that names the low-level call or one
of the old hooks has started a second one.

The files below still do, until the step of #210 that moves them off removes their
line. A file not listed may not start, and a listed file that no longer does must
be taken off. The list is expected to stay empty: at most
`subscription_service.py` may join it while payments are frozen.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "stoa"
GATEWAY = "src/stoa/db/table.py"

FORBIDDEN = (
    "transact_write_items",
    "transact_account_deletion",
    "transact_attachment_write",
    "transact_conversation_write",
    "wire_format_client",
)

ALLOWED: set[str] = set()


def _mentions(text: str) -> list[str]:
    return [
        f"{number}: {name}"
        for number, line in enumerate(text.splitlines(), start=1)
        for name in FORBIDDEN
        if name in line
    ]


def _offenders() -> dict[str, list[str]]:
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == GATEWAY:
            continue
        found = _mentions(path.read_text(encoding="utf-8"))
        if found:
            offenders[relative] = found
    return offenders


def test_no_module_but_the_gateway_sends_a_transaction():
    offenders = _offenders()
    new = {path: lines[:3] for path, lines in offenders.items() if path not in ALLOWED}
    assert not new, f"send it through stoa.db.table.transact instead: {new}"


def test_the_allowlist_names_only_files_that_still_need_it():
    stale = ALLOWED - set(_offenders())
    assert not stale, f"no longer sends its own transaction; remove from ALLOWED: {sorted(stale)}"


def test_the_gateway_is_where_the_call_is_made():
    assert "transact_write_items" in (ROOT / GATEWAY).read_text(encoding="utf-8")


def test_the_gate_sees_what_it_guards():
    assert _mentions("client.transact_write_items(TransactItems=items)\n")
    assert _mentions('hook = getattr(table, "transact_account_deletion", None)\n')
    assert not _mentions("db_table.transact(operations, table=target)\n")
