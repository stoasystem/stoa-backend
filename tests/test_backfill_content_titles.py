"""The content titles backfill names the rows written before #661 as readers see them.

Run against the published-curriculum fixture with `titles` taken off every topic,
unit and lesson row, as production holds the curriculum before the backfill: a dry
run counts and writes nothing, `--apply` gives each row the names
`curriculum_names` shows today, a row rewritten meanwhile is skipped, a row that
names itself keeps its names, and `--verify` finds no name a reader would lose
once the translation table's content entries are gone.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.published_curriculum import ReadCountingTable, curriculum_rows
from scripts import backfill_content_titles as backfill
from stoa.db import table as db_table
from stoa.services import curriculum_cache, curriculum_names

#: A lesson an author named in two languages after #661, which the table does not know.
AUTHORED = {
    "PK": "PRACTICE",
    "SK": "LESSON#authored-lesson",
    "lesson_id": "authored-lesson",
    "unit_id": "brueche-u1",
    "topic_id": "brueche",
    "subject_id": "mathematics",
    "title": "Selbst geschrieben",
    "titles": {"de": "Selbst geschrieben", "en": "Written by hand"},
}


def _before_the_writers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: v for k, v in row.items() if k != "titles"}
        if row["PK"] == "PRACTICE" and row["SK"].split("#", 1)[0] in backfill.KINDS
        else row
        for row in rows
    ]


@pytest.fixture
def table() -> ReadCountingTable:
    table = ReadCountingTable()
    rows = _before_the_writers(curriculum_rows(0.02))
    # A ZAP lesson an author has since named in English only, its own way.
    lesson = next(row for row in rows if row["SK"] == "LESSON#brueche-l2")
    lesson["titles"] = {"de": lesson["title"], "en": "Fractions that are equal"}
    table.seed(*rows, dict(AUTHORED))
    db_table.install(table)
    return table


def _content(table: ReadCountingTable) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == "PRACTICE" and sk.split("#", 1)[0] in backfill.KINDS
    ]


def _shown(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str | None]:
    """What `curriculum_names` names each content row in each language."""
    shown: dict[tuple[str, str], str | None] = {}
    for locale in curriculum_names.LOCALES:
        names = curriculum_names.for_reader(locale, rows=rows)
        for row in rows:
            content_id = backfill._content_id(row)
            shown[(content_id, locale)] = names.name(content_id)
    return shown


def _lost_before(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        for locale in backfill.translations(backfill._content_id(row))
        if locale not in curriculum_names.normalized_titles(row.get("titles"))
    )


def test_a_dry_run_counts_and_writes_nothing(
    table: ReadCountingTable, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=False, verify_rows=False) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    rows = _content(table)
    topics = sum(1 for row in rows if row["SK"].startswith("TOPIC#"))
    assert f"TOPIC: rows {topics} | named already 0 | to write {topics} | of them German only 0" in out
    # Every row but the authored one, which names itself in what the table would give.
    assert f"Rows to write: {len(rows) - 1}" in out
    # A lesson the table has no translation for is listed: it reads German anyway.
    assert "German only (shown in German in every language, before and after):" in out
    assert "  LESSON#kb-mathematics-l0 active: " in out
    assert "[DRY RUN]" in out


def test_apply_names_every_row_as_readers_see_it(table: ReadCountingTable) -> None:
    shown_before = _shown(_content(table))
    stamp_before = table.rows.get((curriculum_cache.STAMP_KEY["PK"], curriculum_cache.STAMP_KEY["SK"]))

    assert backfill.run(table, apply_writes=True, verify_rows=False) == 0

    rows = _content(table)
    assert _shown(rows) == shown_before
    for row in rows:
        assert row["titles"]["de"] == row["title"]
    # The table's names, word for word, and German the row's title.
    assert table.rows[("PRACTICE", "TOPIC#brueche")]["titles"] == {
        "de": "Brüche",
        "en": "Fractions",
        "fr": "Fractions",
        "it": "Frazioni",
    }
    # A row's own name stays; the languages it lacked come from the table.
    own = table.rows[("PRACTICE", "LESSON#brueche-l2")]["titles"]
    assert own["en"] == "Fractions that are equal"
    assert own["fr"] == "Fractions équivalentes"
    assert table.rows[("PRACTICE", "LESSON#authored-lesson")]["titles"] == AUTHORED["titles"]
    # Nothing is left to write, no name is lost without the table, and every
    # container reads the curriculum again.
    assert backfill.plan(rows).writes == []
    assert backfill.check(rows).lost == []
    assert table.rows[(curriculum_cache.STAMP_KEY["PK"], curriculum_cache.STAMP_KEY["SK"])] != stamp_before


def test_verify_lists_the_names_readers_would_lose_until_it_has_run(
    table: ReadCountingTable, capsys: pytest.CaptureFixture[str]
) -> None:
    lost = _lost_before(_content(table))
    assert lost > 0

    assert backfill.run(table, apply_writes=False, verify_rows=True) == 1
    assert f"Names a reader would lose without the table: {lost}" in capsys.readouterr().out

    backfill.run(table, apply_writes=True, verify_rows=False)
    capsys.readouterr()

    assert backfill.run(table, apply_writes=False, verify_rows=True) == 0
    out = capsys.readouterr().out
    assert "Names a reader would lose without the table: 0" in out
    assert "no titles 0" in out


def test_a_row_rewritten_meanwhile_is_skipped(table: ReadCountingTable) -> None:
    planned = backfill.plan(backfill.content_rows(table))
    row, _names = next((row, names) for row, names in planned.writes if row["SK"] == "TOPIC#brueche")
    # A seed run renames the topic between the read and the write.
    table.rows[(row["PK"], row["SK"])]["title"] = "Brüche (neu)"

    outcome = backfill.apply(table, planned)

    assert outcome["changed meanwhile, skipped"] == 1
    assert outcome["written"] == len(planned.writes) - 1
    assert "titles" not in table.rows[(row["PK"], row["SK"])]
    left = backfill.plan(_content(table)).writes
    assert [(row["SK"], names["de"]) for row, names in left] == [("TOPIC#brueche", "Brüche (neu)")]


def test_names_for_takes_german_from_the_title_and_keeps_the_rows_own() -> None:
    assert backfill.names_for(
        {"SK": "UNIT#brueche-u1", "unit_id": "brueche-u1", "title": " Brüche verstehen "}
    ) == {
        "de": "Brüche verstehen",
        "en": "Understanding and reducing fractions",
        "fr": "Comprendre et simplifier les fractions",
        "it": "Capire e semplificare le frazioni",
    }
    assert backfill.names_for(
        {"SK": "LESSON#new", "lesson_id": "new", "title": "Neu", "titles": {"it": "Nuovo"}}
    ) == {"de": "Neu", "it": "Nuovo"}
