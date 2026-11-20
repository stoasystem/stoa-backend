"""How long an Ask answer may be, and what one question reserves (#531).

A multi-step derivative answer, LaTeX and all, ran past the old 2048-token
output cap and failed as `incomplete_output`. The cap is now 4096, and the
prompt gives the model a length budget so most answers end far below it. The
cap is also what a question reserves of the weekly allowance before the model
is called; a question whose reservation no longer fits is refused as the
allowance being used up, even with some of it left (decided on #531).
"""

from __future__ import annotations

import pytest

from fakes.ask_question import _client, _generation, _send
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa import config
from stoa.services import ask_answer

STYLES = ("concise", "encouraging", "vivid")


def test_the_ask_output_cap_is_4096() -> None:
    assert config.Settings(environment="development").bedrock_max_tokens == 4096


def test_a_question_asks_the_model_for_at_most_the_cap(table, model) -> None:
    client = _client()

    response = _send(client, "key-1")

    assert response.status_code == 200, response.text
    assert _generation(client, "key-1")["status"] == "completed"
    assert model.requests[-1]["max_tokens"] == config.settings().bedrock_max_tokens


def test_the_prompt_gives_a_new_answer_a_length_budget() -> None:
    prompt = ask_answer.SYSTEM_PROMPT

    assert "max 300 words in all" in prompt
    assert f"at most {ask_answer.ANSWER_MAX_STEPS} steps" in prompt
    assert f"at most {ask_answer.ANSWER_MAX_HINTS} hints" in prompt
    assert f"at most {ask_answer.ANSWER_MAX_SIMILAR_EXERCISES} similar exercises" in prompt
    assert f"at most {ask_answer.ANSWER_MAX_KNOWLEDGE_POINTS} knowledge points" in prompt
    assert "Write each calculation once" in prompt


def test_the_budget_comes_before_the_follow_up_rule_that_empties_the_lists() -> None:
    # A follow-up still leaves steps, hints and exercises empty: the budget is
    # a ceiling for a new answer, never a reason to fill a follow-up.
    prompt = ask_answer.SYSTEM_PROMPT

    assert prompt.index("at most 6 steps") < prompt.index("When the student follows up")


@pytest.mark.parametrize("style", STYLES)
def test_no_style_lifts_the_length_budget(style: str) -> None:
    rule = ask_answer.answer_style_rule(style)

    assert "300 words, the counts of steps, hints, exercises and knowledge points" in rule


def test_the_prompt_still_formats_for_every_language() -> None:
    # The budget sits inside a prompt filled in with `str.format`: a stray
    # brace in it would break every answer.
    for language, name in (("de", "German"), ("en", "English"), ("fr", "French"), ("it", "Italian")):
        filled = ask_answer.SYSTEM_PROMPT.format(
            subject="math",
            grade="Grade 6",
            language=language,
            language_name=name,
            subject_context="",
        )
        assert "at most 6 steps" in filled
