"""Reads, paging and conditional refusals reach DynamoDB through the table gateway (#298).

The table gateway (`stoa.db.table`, #210) is where the table is taken from, where a
read goes on page after page, and where a refusal is judged. A module below
`src/stoa` that does one of these itself has started a second one:

- `get_table`: calls `get_table()` for a table of its own instead of reading through
  the gateway;
- `paging`: names `ExclusiveStartKey`, which is a paging loop of its own
  (`db_table.pages` / `db_table.rows` are the ones);
- `conditional_check`: matches the `ConditionalCheckFailedException` string instead of
  catching the gateway's `WriteRefused`.

`ALLOWED` names every file that still does, and which of the three. It is grouped
by domain, and each group is one batch migration of #210: a batch moves its files
onto the gateway and deletes their lines - a file may not keep a rule it no longer
breaks, and no file may start breaking one. When the batches are done the only
entry left is `services/subscription_service.py`, while payments are frozen.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "stoa"
GATEWAY = "db/table.py"

RULES = {
    # A call, not the definition in `db/dynamodb.py` and not a name passed along.
    "get_table": re.compile(r"(?<!def )\bget_table\(\)"),
    "paging": re.compile(r"\bExclusiveStartKey\b"),
    "conditional_check": re.compile(r"ConditionalCheckFailedException"),
}

ALLOWED: dict[str, dict[str, set[str]]] = {
    "payments, frozen (stays until payments resume)": {
        "services/subscription_service.py": {"get_table", "paging", "conditional_check"},
    },
}


def _breaks(text: str) -> set[str]:
    return {rule for rule, pattern in RULES.items() if pattern.search(text)}


def _offenders() -> dict[str, set[str]]:
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(SOURCE).as_posix()
        if relative == GATEWAY:
            continue
        found = _breaks(path.read_text(encoding="utf-8"))
        if found:
            offenders[relative] = found
    return offenders


def _allowed() -> dict[str, set[str]]:
    return {path: rules for group in ALLOWED.values() for path, rules in group.items()}


def test_no_module_starts_reading_or_judging_the_table_itself():
    allowed = _allowed()
    new = {
        path: sorted(rules - allowed.get(path, set()))
        for path, rules in _offenders().items()
        if rules - allowed.get(path, set())
    }
    assert not new, f"read and judge through stoa.db.table instead: {new}"


def test_the_allowlist_names_only_what_files_still_do():
    offenders = _offenders()
    stale = {
        path: sorted(rules - offenders.get(path, set()))
        for path, rules in _allowed().items()
        if rules - offenders.get(path, set())
    }
    assert not stale, f"no longer needed; remove from ALLOWED: {stale}"


def test_each_file_is_in_one_batch():
    paths = [path for group in ALLOWED.values() for path in group]
    assert len(paths) == len(set(paths))


def test_the_gateway_is_where_paging_happens():
    gateway = (SOURCE / GATEWAY).read_text(encoding="utf-8")
    assert RULES["paging"].search(gateway)


def test_the_gate_sees_what_it_guards():
    assert _breaks("    target = table or get_table()") == {"get_table"}
    assert _breaks('        request["ExclusiveStartKey"] = cursor') == {"paging"}
    assert _breaks('    if code == "ConditionalCheckFailedException":') == {"conditional_check"}
    assert not _breaks("def get_table() -> object:")
    assert not _breaks("table_factory=get_table,")
    assert not _breaks('for page in db_table.pages("scan", start=cursor):')
