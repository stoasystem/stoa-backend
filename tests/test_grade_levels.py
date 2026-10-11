"""One vocabulary for year groups: the codes, their four languages, and the prompt.

The grade box took free text and production ended up holding five different
things - nothing, two spaces, "Grade 6", "Sek1" and "14" - while every
curriculum row spelled its year group `grade_6_primary`. Nothing ever joined
the two, and the single place a grade is read, the assistant's system prompt,
was handed whatever the student typed: "The student is in 14".

These check the closed set end to end, over the whole set rather than one
member of it, and each positive claim is paired with the negative that would
otherwise let an implementation returning nothing pass.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable, as_stored

from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import students
from stoa.security import route_authorization
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import ai_service, learning_profile_service, message_catalog

from audit_helpers import MemoryAuthorizationAuditSink
from scripts import backfill_student_grade_codes as backfill


LOCALES = ("de", "en", "fr", "it")

# What production actually holds, read off the live table on 2026-10-11:
# 37 blanks, 1 field of two spaces, 29 "Grade 6", 9 "Sek1", 1 "14".
PRODUCTION_SPELLINGS = ("", "  ", "Grade 6", "Sek1", "14")


# ── The code set and its labels ──────────────────────────────────────────────

def test_the_curriculum_spelling_is_the_one_the_profile_uses():
    """The codes are the catalog's own, not a second vocabulary beside it.

    `grade_6_primary` is what `seed_practice.SUBJECT["grade_levels"]` writes on
    every lesson, topic and challenge row; the rest are built the same way.
    """
    assert "grade_6_primary" in learning_profile_service.GRADE_LEVEL_CODES
    assert all(
        code.startswith("grade_") for code in learning_profile_service.GRADE_LEVEL_CODES
    )
    assert len(set(learning_profile_service.GRADE_LEVEL_CODES)) == len(
        learning_profile_service.GRADE_LEVEL_CODES
    )


def test_every_code_is_written_out_in_all_four_languages():
    """The whole set against the whole catalog, not one code against one string.

    A code with no line in the catalog reaches the model as a KeyError or, once
    the lookup has a fallback, as somebody else's language.
    """
    for code in learning_profile_service.GRADE_LEVEL_CODES:
        variants = message_catalog.TEXT[f"grade.{code}"]
        assert set(variants) == set(LOCALES), code
        assert all(variants[locale].strip() for locale in LOCALES), code
        # Four entries that are the same string are three missing translations
        # wearing the fourth's clothes.
        assert len(set(variants.values())) == len(LOCALES), code


# ── The four languages name the same school year, not four different ones ────
#
# "Four entries, all different" is satisfied by four different wrong years, and
# that is exactly what shipped first: `6e année primaire` is two years younger
# than `6. Primarklasse`, and `6ª elementare` is a year Ticino does not have.
#
# So the judgement is the HarmoS year - the one numbering the whole country
# shares - and each language area's own rule for saying it. The rules are
# written out here rather than read back from the catalog, so a label that
# disagrees with the anchor fails even though it is a perfectly good French
# sentence. What this still cannot prove is the anchor itself: that
# `grade_6_primary` is HarmoS 8 is sourced in the comment above
# `GRADE_LEVEL_HARMOS_YEARS`, not derived here.

def _expected_labels(harmos: int) -> dict[str, str]:
    """The same HarmoS year, as each language area numbers it."""
    zurich = harmos - 2  # Zurich does not count the two kindergarten years.
    if harmos <= 8:
        de = f"{zurich}. Primarklasse"
        en = f"year {zurich} of primary school"
        fr = f"{harmos}e année primaire ({harmos}P)"  # Romandie counts HarmoS.
    else:
        de = f"{zurich}. Klasse (Sekundarstufe I)"
        en = f"year {zurich}, lower secondary school"
        fr = f"{harmos}e année (secondaire I)"
    # Ticino: five years of elementare (HarmoS 3-7), four of media (8-11).
    it = f"{harmos - 2}ª elementare" if harmos <= 7 else f"{harmos - 7}ª media"
    return {"de": de, "en": en, "fr": fr, "it": it}


def test_the_anchor_covers_the_code_set_and_nothing_else():
    assert set(learning_profile_service.GRADE_LEVEL_HARMOS_YEARS) == set(
        learning_profile_service.GRADE_LEVEL_CODES
    )


def test_each_language_names_the_year_its_own_school_system_calls_it():
    for code, harmos in learning_profile_service.GRADE_LEVEL_HARMOS_YEARS.items():
        if harmos is None:
            continue
        assert message_catalog.TEXT[f"grade.{code}"] == _expected_labels(harmos), code


def test_the_year_groups_run_from_the_first_primary_year_to_the_last_compulsory_one():
    """The anchor is a straight run, so no year is skipped or counted twice."""
    years = [
        harmos
        for harmos in learning_profile_service.GRADE_LEVEL_HARMOS_YEARS.values()
        if harmos is not None
    ]
    assert years == list(range(3, 12))


@pytest.mark.parametrize(
    ("locale", "stage", "unsaid"),
    [
        ("de", "Sekundarstufe I", "nicht angegeben"),
        ("en", "lower secondary school", "no year given"),
        ("fr", "secondaire I", "non précisée"),
        ("it", "scuola media", "non indicato"),
    ],
)
def test_the_stage_band_names_a_stage_and_says_the_year_is_missing(locale, stage, unsaid):
    label = message_catalog.TEXT["grade.grade_secondary_i"][locale]
    assert stage in label
    assert unsaid in label
    # Negative control: it must not claim a year it was never told.
    assert not any(character.isdigit() for character in label)


def test_the_catalog_holds_no_year_group_the_code_set_disowns():
    """Neither table may grow a member the other has never heard of."""
    catalogued = {
        key.removeprefix("grade.") for key in message_catalog.TEXT if key.startswith("grade.")
    }
    assert catalogued == set(learning_profile_service.GRADE_LEVEL_CODES)


@pytest.mark.parametrize("locale", LOCALES)
def test_a_label_is_read_in_the_language_asked_for(locale):
    label = learning_profile_service.grade_label("grade_6_primary", locale)
    assert label == message_catalog.TEXT["grade.grade_6_primary"][locale]
    # Negative control: the other three languages are not what came back.
    others = [other for other in LOCALES if other != locale]
    assert all(
        label != message_catalog.TEXT["grade.grade_6_primary"][other] for other in others
    )


def test_an_unsupported_locale_still_gets_a_year_group():
    assert learning_profile_service.grade_label("grade_6_primary", "es") == (
        message_catalog.TEXT["grade.grade_6_primary"]["de"]
    )


# ── Reading what is stored ───────────────────────────────────────────────────

def test_every_code_reads_back_as_itself():
    for code in learning_profile_service.GRADE_LEVEL_CODES:
        assert learning_profile_service.resolve_grade_code(code) == code


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("Grade 6", "grade_6_primary"), ("sek1", "grade_secondary_i"), ("SEK1", "grade_secondary_i")],
)
def test_the_free_text_already_in_the_table_is_understood(stored, expected):
    assert learning_profile_service.resolve_grade_code(stored) == expected


@pytest.mark.parametrize("stored", ["", "   ", None])
def test_saying_nothing_is_not_the_same_as_saying_something_unreadable(stored):
    assert learning_profile_service.resolve_grade_code(stored) == ""


@pytest.mark.parametrize("stored", ["14", "6", "sixth form", "grade_13_secondary"])
def test_a_value_no_one_can_read_is_reported_as_such(stored):
    """"14" is an age in a year-group box. Nothing is guessed from it."""
    assert learning_profile_service.resolve_grade_code(stored) is None


# ── The closed set at the door ───────────────────────────────────────────────

def test_the_judgement_a_write_will_be_held_to_once_the_client_sends_codes():
    """`normalize_grade` is the door for the next change; nothing calls it yet.

    It is specified and tested now so the step that adds it to the route is a
    one-line change, and so the set it judges against cannot quietly drift.
    """
    for code in learning_profile_service.GRADE_LEVEL_CODES:
        assert learning_profile_service.normalize_grade(code) == code
    for refused in ("Grade 6", "Sek1", "14", "6. Klasse", "grade_6", "GRADE_6_PRIMARY"):
        with pytest.raises(ValueError):
            learning_profile_service.normalize_grade(refused)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_not_saying_stays_legal_at_the_door(blank):
    assert learning_profile_service.normalize_grade(blank) == ""


def _actor(user_id="student-1"):
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        "student",
        (),
    )


@pytest.fixture
def profile_client(monkeypatch):
    """The real route, with the store and its writes recorded."""
    profile = {
        "user_id": "student-1",
        "role": "student",
        "account_status": "active",
        "name": "Student One",
        "grade": "Sek1",
        "primary_subjects": ["math"],
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    writes: list[dict] = []
    monkeypatch.setattr(
        route_authorization.user_repo, "get_user", lambda user_id, **_kwargs: dict(profile)
    )
    monkeypatch.setattr(students.user_repo, "get_user", lambda user_id, **_kwargs: dict(profile))

    def _update(user_id, **kwargs):
        writes.append(kwargs)
        stored = dict(profile)
        values = kwargs.get("expression_attribute_values") or {}
        if ":g" in values:
            stored["grade"] = values[":g"]
        return stored

    monkeypatch.setattr(students.user_repo, "update_profile_fields", _update)

    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app), writes


def test_every_code_is_accepted_by_the_profile_route(profile_client):
    client, writes = profile_client
    for code in learning_profile_service.GRADE_LEVEL_CODES:
        response = client.patch("/students/me/profile", json={"grade": code})
        assert response.status_code == 200, code
        assert response.json()["grade"] == code
    assert len(writes) == len(learning_profile_service.GRADE_LEVEL_CODES)


@pytest.mark.parametrize(
    "typed",
    # Word for word what the live client's own hint asks the student to type,
    # in each of its four languages.
    ["6. Klasse", "Year 6", "6e année", "6ª classe", "Sek1", "14"],
)
def test_the_text_the_live_client_asks_for_is_still_accepted(profile_client, typed):
    """The closed set is not yet enforced at this door, and must not be.

    The grade box on the web client is free text whose hint says 'Zum Beispiel
    «6. Klasse»'. Refusing that here answers a student who did exactly as asked
    with "not saved, try again" - a permanent failure worded as a retryable one
    - every time, for as long as that client is the one deployed. The door
    closes in the same change that gives the client a dropdown.
    """
    client, writes = profile_client
    response = client.patch("/students/me/profile", json={"grade": typed})
    assert response.status_code == 200
    assert response.json()["grade"] == typed
    assert [write["expression_attribute_values"][":g"] for write in writes] == [typed]


@pytest.mark.parametrize("typed", ["6. Klasse", "Year 6", "14", "<script>alert(1)</script>"])
def test_what_that_door_lets_through_still_cannot_reach_the_model(typed):
    """Which is why the open door is safe: the prompt refuses it, not the write.

    Every one of these is stored as sent and none of them is said to the model.
    """
    prompt = _system_prompt(grade=typed)
    assert typed not in prompt
    assert f"The student is in {ai_service.UNREADABLE_GRADE}:" in prompt


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_student_who_has_not_said_may_still_save_their_profile(profile_client, blank):
    """#50: the grade is asked for later than the account is opened.

    Stored as sent, whitespace included, because this step does not touch the
    write. What matters downstream is that both reach the model as the same
    "nobody said" sentence, which `resolve_grade_code` decides and the prompt
    tests pin.
    """
    client, writes = profile_client
    response = client.patch("/students/me/profile", json={"grade": blank})
    assert response.status_code == 200
    assert response.json()["grade"] == blank
    assert [write["expression_attribute_values"][":g"] for write in writes] == [blank]
    assert learning_profile_service.resolve_grade_code(blank) == ""


def test_a_stored_legacy_grade_is_still_readable(profile_client):
    """Rows written before the codes existed are read back, not 503'd."""
    client, _writes = profile_client
    response = client.get("/students/me/profile")
    assert response.status_code == 200
    assert response.json()["grade"] == "Sek1"


# ── What the model is told ───────────────────────────────────────────────────

class _CapturingBedrockClient:
    def __init__(self) -> None:
        self.request_body: dict | None = None

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        self.request_body = json.loads(body)
        payload = {
            "id": "msg_test_1",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [
                {
                    "text": json.dumps(
                        {
                            "steps": ["step one"],
                            "answer": "42",
                            "hints": [],
                            "knowledge_points": [],
                            "suggest_teacher": False,
                        }
                    )
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return {
            "ResponseMetadata": {"RequestId": "req-test-1"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }


def _system_prompt(*, grade: str, language: str = "de") -> str:
    client = _CapturingBedrockClient()
    ai_service.get_ai_answer(
        content="how do I add fractions?",
        subject="math",
        grade=grade,
        language=language,
        client=client,
        effect_id="effect-grade-1",
    )
    assert client.request_body is not None
    return client.request_body["system"]


@pytest.mark.parametrize("language", LOCALES)
def test_the_year_group_reaches_the_model_in_the_answer_language(language):
    prompt = _system_prompt(grade="grade_6_primary", language=language)
    named = message_catalog.TEXT["grade.grade_6_primary"][language]
    assert f"The student is in {named}:" in prompt
    # Negative control: no other language's wording came along, and the stored
    # code itself never appears.
    for other in LOCALES:
        if other != language:
            assert message_catalog.TEXT["grade.grade_6_primary"][other] not in prompt
    assert "grade_6_primary" not in prompt


def test_every_code_reaches_the_model_as_words_and_never_as_a_code():
    for code in learning_profile_service.GRADE_LEVEL_CODES:
        prompt = _system_prompt(grade=code, language="de")
        assert f"The student is in {message_catalog.TEXT[f'grade.{code}']['de']}:" in prompt
        assert code not in prompt


@pytest.mark.parametrize("blank", ["", "   "])
def test_the_sentence_for_a_student_who_said_nothing_is_untouched(blank):
    """#50's wording, to the word. It is not this card's to rewrite."""
    prompt = _system_prompt(grade=blank)
    assert ai_service.UNKNOWN_GRADE == (
        "an unknown year group (none was given; pitch it at lower secondary school)"
    )
    assert f"The student is in {ai_service.UNKNOWN_GRADE}: use that to choose the depth" in prompt
    assert (
        f"far above {ai_service.UNKNOWN_GRADE}, first give a short accessible explanation"
        in prompt
    )
    assert "The student is in :" not in prompt


@pytest.mark.parametrize("stored", ["14", "sixth form"])
def test_a_value_the_platform_cannot_read_never_reaches_the_model(stored):
    """The defect itself: the model was told "The student is in 14"."""
    prompt = _system_prompt(grade=stored)
    assert f"The student is in {stored}" not in prompt
    assert f"The student is in {ai_service.UNREADABLE_GRADE}:" in prompt
    # And it is not told the profile is empty, because the profile is not empty.
    assert ai_service.UNKNOWN_GRADE not in prompt


def test_free_text_still_in_the_table_is_named_properly_before_the_backfill_runs():
    prompt = _system_prompt(grade="Sek1", language="de")
    assert "The student is in Sek1" not in prompt
    assert (
        f"The student is in {message_catalog.TEXT['grade.grade_secondary_i']['de']}:" in prompt
    )


# ── The backfill ─────────────────────────────────────────────────────────────

def _seeded_table() -> FakeTable:
    table = FakeTable()
    for index, stored in enumerate(PRODUCTION_SPELLINGS):
        user_id = f"student-{index}"
        table.rows[(f"USER#{user_id}", "PROFILE")] = as_stored(
            {
                "PK": f"USER#{user_id}",
                "SK": "PROFILE",
                "user_id": user_id,
                "role": "student",
                "account_status": "active",
                "grade": stored,
            }
        )
    table.rows[("USER#teacher-1", "PROFILE")] = as_stored(
        {
            "PK": "USER#teacher-1",
            "SK": "PROFILE",
            "user_id": "teacher-1",
            "role": "teacher",
            "grade": "Grade 6",
        }
    )
    return table


def _grades(table: FakeTable) -> dict[str, str]:
    return {
        str(row["user_id"]): str(row.get("grade", ""))
        for row in table.rows.values()
        if row.get("SK") == "PROFILE"
    }


def test_a_plain_run_writes_nothing(capsys):
    """Report only is the default; `--apply` is the only way to a write."""
    table = _seeded_table()
    before = _grades(table)

    result = backfill.run(table, apply=False)

    assert _grades(table) == before
    assert table.calls["update_item"] == 0
    assert table.calls["put_item"] == 0
    assert "[REPORT ONLY]" in capsys.readouterr().out
    # Negative control: it did find the two rows it would have written, so an
    # implementation that simply does nothing cannot pass this pair.
    assert sorted(code for _profile, code in result.rewrite) == [
        "grade_6_primary",
        "grade_secondary_i",
    ]


def test_applying_rewrites_the_two_spellings_and_leaves_the_rest_alone():
    table = _seeded_table()

    backfill.run(table, apply=True)

    assert _grades(table) == {
        "student-0": "",
        "student-1": "  ",
        "student-2": "grade_6_primary",
        "student-3": "grade_secondary_i",
        "student-4": "14",
        "teacher-1": "Grade 6",
    }


def test_the_age_in_the_year_group_box_is_reported_and_never_written(capsys):
    table = _seeded_table()

    result = backfill.run(table, apply=True)

    assert [stored for _user, stored in result.unmappable] == ["14"]
    assert _grades(table)["student-4"] == "14"
    assert "UNMAPPABLE" in capsys.readouterr().out


def test_running_it_twice_changes_nothing_the_second_time():
    table = _seeded_table()
    backfill.run(table, apply=True)
    settled = _grades(table)

    second = backfill.run(table, apply=True)

    assert second.rewrite == []
    assert _grades(table) == settled


@pytest.mark.parametrize("page_item_cap", [1, 2, 7, 44])
def test_every_page_of_the_table_is_read(page_item_cap):
    """A scan that stops at the first page reports a sample as if it were the census.

    The production table holds conversations and messages beside the profiles,
    so this scan pages whatever the profiles cost. Nothing else in the suite
    notices: with the loop cut down to `return profiles` the fixtures above are
    small enough to arrive in one page and stay green.
    """
    table = FakeTable(page_item_cap=page_item_cap)
    for index in range(45):
        user_id = f"student-{index:03d}"
        table.rows[(f"USER#{user_id}", "PROFILE")] = as_stored(
            {
                "PK": f"USER#{user_id}",
                "SK": "PROFILE",
                "user_id": user_id,
                "role": "student",
                "grade": "Grade 6",
            }
        )

    result = backfill.run(table, apply=False)

    assert len(backfill.scan_profiles(table)) == 45
    assert len(result.rewrite) == 45
    # And it really did take more than one request to get them.
    assert table.calls["scan"] > 1


def test_the_backfill_only_writes_what_the_read_path_already_understands():
    """One table, so the script and the prompt cannot drift apart."""
    table = _seeded_table()
    result = backfill.run(table, apply=False)
    for _profile, code in result.rewrite:
        assert code in learning_profile_service.GRADE_LEVEL_CODES
