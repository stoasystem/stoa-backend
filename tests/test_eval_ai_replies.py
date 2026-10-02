"""#43 / card 078: the AI-reply evaluation, run offline against a fake model.

These prove the evaluation's own logic - the question set, the readings, the
two poisonings and the cost guard - without a paid call. What the real model
answers is only shown by a real run (the readings recorded on #43).

The fake model answers in whatever language the system prompt names and
declines when the prompt ties the subject to the grade, which is what the real
one was seen to do before E1. So both poisonings move the readings here the
way the card expects them to move against Bedrock - which proves the
arithmetic, not the model: that the prompt really reads as before E1 is pinned
separately, on the prompt itself.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import re
from typing import Any

import pytest

from stoa.services import ai_service
from stoa.services.curriculum_service import SUPPORTED_SUBJECTS

import eval_ai_replies as evaluation


ROOT = Path(__file__).resolve().parents[1]

REPLIES = {
    "German": (
        ["Zuerst schauen wir uns die Aufgabe an und schreiben auf, was wir wissen.",
         "Dann rechnen wir den nächsten Schritt mit dem Beispiel aus."],
        "Du kannst das Ergebnis jetzt selbst prüfen, wenn du die Schritte wiederholst.",
    ),
    "English": (
        ["First we look at the task and write down what we know.",
         "Then we work out the next step with the example."],
        "You can now check the result yourself if you repeat the steps.",
    ),
    "French": (
        ["D'abord, on regarde la tâche et on écrit ce que nous savons.",
         "Ensuite, on calcule l'étape suivante avec l'exemple."],
        "Tu peux maintenant vérifier le résultat si tu refais les étapes.",
    ),
    "Italian": (
        ["Prima guardiamo il compito e scriviamo che cosa sappiamo.",
         "Poi calcoliamo il passo successivo con l'esempio."],
        "Ora puoi controllare il risultato se ripeti i passi.",
    ),
}
REFUSALS = {
    "German": "Diese Frage kann ich nicht beantworten, sie liegt ausserhalb deiner Stufe.",
    "English": "I cannot answer this question, it is outside your level.",
    "French": "Je ne peux pas répondre, cette question est en dehors de ton niveau.",
    "Italian": "Non posso rispondere, la domanda è fuori dal tuo livello.",
}


class FakeModel:
    """Answers in the language the prompt names; declines under the pre-E1 sentence."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke_model(self, *, modelId: str, body: str):  # noqa: N803 - boto3 casing
        self.calls += 1
        request = json.loads(body)
        system = request["system"] if isinstance(request["system"], str) else json.dumps(
            request["system"]
        )
        language = re.search(r"OUTPUT LANGUAGE: (\w+)", system).group(1)
        if re.search(r"related to \w+ at .+? level\.", system):
            content = {"steps": [], "answer": REFUSALS[language], "hints": [],
                       "knowledge_points": [], "suggest_teacher": False}
        else:
            steps, answer = REPLIES[language]
            content = {"steps": steps, "answer": answer, "hints": [],
                       "knowledge_points": [], "suggest_teacher": False}
        payload = {
            "id": f"msg_{self.calls}",
            "model": modelId,
            "stop_reason": "end_turn",
            "content": [{"text": json.dumps(content, ensure_ascii=False)}],
            "usage": {"input_tokens": 800, "output_tokens": 300},
        }
        return {
            "ResponseMetadata": {"RequestId": f"req-{self.calls}"},
            "body": io.BytesIO(json.dumps(payload).encode()),
        }


def _asker(model: FakeModel):
    def ask(item: dict[str, Any]):
        result = ai_service.get_ai_answer(
            content=item["question"],
            subject=item["subject"],
            grade=item["grade"],
            language=item["language"],
            client=model,
            effect_id=f"eval-{item['id']}",
        )
        return result.content, result.usage.input_tokens, result.usage.output_tokens

    return ask


@pytest.fixture
def items() -> list[dict[str, Any]]:
    return evaluation.load_questions()


# --- The question set ---


def test_the_set_covers_every_language_subject_and_difficulty(items) -> None:
    in_syllabus = [item for item in items if not item["out_of_syllabus"]]
    combos = {(i["language"], i["subject"], i["difficulty"]) for i in in_syllabus}
    assert combos == {
        (language, subject, difficulty)
        for language in evaluation.LANGUAGES
        for subject in SUPPORTED_SUBJECTS
        for difficulty in ("easy", "hard")
    }
    assert len(in_syllabus) == 32


def test_the_out_of_syllabus_group_is_in_subject_and_above_the_grade(items) -> None:
    beyond = [item for item in items if item["out_of_syllabus"]]
    assert len(beyond) == 8
    assert {item["subject"] for item in beyond} == {"math", "physics"}
    assert {item["language"] for item in beyond} == set(evaluation.LANGUAGES)


def test_every_question_expects_its_own_language(items) -> None:
    for item in items:
        assert item["expected_language"] == item["language"]


def test_the_forbidden_terms_are_the_allowlists_own() -> None:
    allowlist = json.loads(evaluation.TERM_ALLOWLIST.read_text())
    literals = {entry["literal"].lower() for entry in allowlist["entries"]}
    assert set(evaluation.forbidden_terms()) == literals
    assert evaluation.LEGACY_TERM in literals


# --- Reading one reply ---


@pytest.mark.parametrize("language", ["German", "English", "French", "Italian"])
def test_each_language_is_recognised(language) -> None:
    steps, answer = REPLIES[language]
    code = {"German": "de", "English": "en", "French": "fr", "Italian": "it"}[language]
    assert evaluation.detect_language(" ".join([*steps, answer])) == code


def test_a_formula_alone_decides_no_language() -> None:
    assert evaluation.detect_language("$$x^2 + 2x + 1 = (x+1)^2$$ 3/4") is None


def _item(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "it-math-easy", "language": "it", "subject": "math", "grade": "Grade 6",
        "question": "?", "expected_language": "it", "out_of_syllabus": False, **overrides,
    }


TERMS = [evaluation.LEGACY_TERM, evaluation.LEGACY_TERM + "s"]


def test_a_reply_in_the_asked_language_reads_clean() -> None:
    steps, answer = REPLIES["Italian"]
    reading = evaluation.read_reply(_item(), {"steps": steps, "answer": answer}, terms=TERMS)
    assert reading.language_ok and not reading.mixed and not reading.refused
    assert reading.term_violations == 0


def test_a_reply_in_another_language_is_counted() -> None:
    steps, answer = REPLIES["German"]
    reading = evaluation.read_reply(_item(), {"steps": steps, "answer": answer})
    assert reading.detected_language == "de"
    assert not reading.language_ok


def test_a_part_in_another_language_makes_a_reply_mixed() -> None:
    steps, answer = REPLIES["Italian"]
    reading = evaluation.read_reply(
        _item(), {"steps": [*steps, REPLIES["English"][0][0]], "answer": answer}
    )
    assert reading.language_ok
    assert reading.mixed
    assert reading.mixed_segments == [REPLIES["English"][0][0][:120]]


def test_an_example_in_the_language_being_learned_is_not_mixing() -> None:
    steps, answer = REPLIES["Italian"]
    example = "Ich gehe nach Hause, weil ich müde bin und es spät ist."
    reading = evaluation.read_reply(
        _item(subject="german"), {"steps": [*steps, example], "answer": answer}
    )
    assert not reading.mixed


def test_each_use_of_a_legacy_term_counts_once() -> None:
    steps, answer = REPLIES["English"]
    word = evaluation.LEGACY_TERM
    reading = evaluation.read_reply(
        _item(language="en", expected_language="en"),
        {"steps": [*steps, f"Ask your {word.title()} or other {word}s for help."],
         "answer": answer},
        terms=TERMS,
    )
    assert reading.term_violations == 2


def test_other_words_that_start_the_same_way_do_not_count() -> None:
    steps, answer = REPLIES["English"]
    word = evaluation.LEGACY_TERM
    reading = evaluation.read_reply(
        _item(language="en", expected_language="en"),
        {"steps": [*steps, f"Watch the {word}ial, then the {word}iel and the {word}ium."],
         "answer": answer},
        terms=TERMS,
    )
    assert reading.term_violations == 0


def test_handing_over_to_a_teacher_is_read_beside_refusals(items) -> None:
    steps, answer = REPLIES["Italian"]
    reading = evaluation.read_reply(
        _item(out_of_syllabus=True),
        {"steps": steps, "answer": answer, "suggest_teacher": True},
    )
    assert reading.suggested_teacher and not reading.refused
    summary = evaluation.summarize([reading])
    assert summary["suggest_teacher_pct_out_of_syllabus"] == 100.0
    assert summary["refusal_pct_out_of_syllabus"] == 0.0


def test_a_declining_reply_counts_as_a_refusal() -> None:
    reading = evaluation.read_reply(
        _item(out_of_syllabus=True), {"steps": [], "answer": REFUSALS["Italian"]}
    )
    assert reading.refused


def test_a_one_step_reply_that_declines_counts_as_a_refusal() -> None:
    reading = evaluation.read_reply(
        _item(language="en", expected_language="en", out_of_syllabus=True),
        {"steps": ["I can only answer questions for your year."], "answer": "Sorry."},
    )
    assert reading.refused


def test_a_reply_that_declines_over_several_steps_counts_as_a_refusal() -> None:
    # The pre-E1 run of 2026-10-02 (#43): fr-math-beyond declined in its
    # second of three steps and was read as an explanation.
    reading = evaluation.read_reply(
        _item(language="fr", expected_language="fr", out_of_syllabus=True),
        {"steps": ["Ce sujet dépasse le programme de mathématiques de 6e année. Les intégrales "
                   "sont un concept du lycée avancé ou de l'université.",
                   "Je suis ici pour t'aider avec les mathématiques de niveau 6e. Je ne peux pas "
                   "répondre à cette question.",
                   "Essaie de poser une question sur les fractions ou la géométrie."],
         "answer": "Pose-moi une question de ton niveau !"},
    )
    assert reading.refused


def test_the_report_keeps_the_whole_reply_so_it_can_be_read_again() -> None:
    steps = ["Step one says a lot more than two hundred and forty characters. " * 5, "Two."]
    reading = evaluation.read_reply(_item(), {"steps": steps, "answer": "Done."})
    assert reading.reply == {"steps": steps, "answer": "Done."}


def test_saying_it_is_advanced_and_then_explaining_is_not_a_refusal() -> None:
    # What a reply that follows E1 does with a question far above the grade.
    reading = evaluation.read_reply(
        _item(language="en", expected_language="en", out_of_syllabus=True),
        {"steps": ["This is too advanced for Grade 6, but here is the idea: a derivative "
                   "tells you how fast something changes.",
                   "Think of the speedometer in a car: it shows how fast the distance changes."],
         "answer": "You will learn the exact rule later; for now the idea is enough."},
    )
    assert not reading.refused


def test_an_ordinary_word_like_outside_is_not_a_refusal() -> None:
    reading = evaluation.read_reply(
        _item(language="en", expected_language="en"),
        {"steps": ["The air outside the lab is colder than the air inside the lab."],
         "answer": "So the warm air rises when it gets out."},
    )
    assert not reading.refused


# --- The two poisonings, through the real prompt builder ---


def test_the_language_poisoning_names_german_for_everyone_and_is_undone() -> None:
    with evaluation.poisoned("language-german"):
        assert ai_service.language_name("it") == "German"
    assert ai_service.language_name("it") == "Italian"


def test_the_pre_e1_poisoning_puts_back_both_passages_and_is_undone() -> None:
    before = ai_service.SYSTEM_PROMPT
    with evaluation.poisoned("pre-e1"):
        poisoned_prompt = ai_service.SYSTEM_PROMPT
    assert ai_service.SYSTEM_PROMPT == before
    for current, old in evaluation.E1_CHANGES:
        assert old in poisoned_prompt
        assert current not in poisoned_prompt
    # Nothing of E1 is left for the old prompt to argue with.
    assert "never to decide whether a question deserves an answer" not in poisoned_prompt
    assert "Reject only questions outside" not in poisoned_prompt


def test_the_pre_e1_prompt_is_the_prompt_before_e1(monkeypatch) -> None:
    # The two passages, as they read in the commit before E1 (04fd9737).
    import subprocess

    shown = subprocess.run(
        ["git", "show", "04fd9737^:src/stoa/services/ai_service.py"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if shown.returncode != 0:
        pytest.skip("this checkout has no history before E1 (a shallow clone)")
    before_e1 = shown.stdout
    namespace: dict[str, Any] = {}
    start = before_e1.index('SYSTEM_PROMPT = """')
    end = before_e1.index('"""', start + len('SYSTEM_PROMPT = """')) + 3
    exec(before_e1[start:end], namespace)  # noqa: S102 - a string literal from our own history
    for _current, old in evaluation.E1_CHANGES:
        assert old in namespace["SYSTEM_PROMPT"]


def test_the_pre_e1_poisoning_refuses_to_run_once_the_prompt_moved_on(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "SYSTEM_PROMPT", "something else entirely")
    with pytest.raises(evaluation.EvalError, match="E1"):
        with evaluation.poisoned("pre-e1"):
            pass


# --- Whole runs against the fake model ---


def test_a_clean_run_reads_full_consistency_and_no_refusals(items) -> None:
    summary = evaluation.summarize(evaluation.run(items, ask=_asker(FakeModel())))
    assert summary["replies"] == 40 and summary["errors"] == 0
    assert summary["language_consistency_pct"] == 100.0
    assert summary["mixed_language_replies"] == 0
    assert summary["term_violations"] == 0
    assert summary["refusal_pct_out_of_syllabus"] == 0.0
    assert summary["tokens"] == {"input": 40 * 800, "output": 40 * 300}


def test_naming_german_for_everyone_drops_consistency_to_a_quarter(items) -> None:
    summary = evaluation.summarize(
        evaluation.run(items, ask=_asker(FakeModel()), poison="language-german")
    )
    assert summary["language_consistency_pct"] == 25.0


def test_the_pre_e1_sentence_raises_the_refusal_rate(items) -> None:
    beyond = evaluation.select(items, "out-of-syllabus")
    summary = evaluation.summarize(
        evaluation.run(beyond, ask=_asker(FakeModel()), poison="pre-e1")
    )
    assert summary["refusal_pct_out_of_syllabus"] == 100.0


def test_a_failed_call_is_recorded_and_the_run_goes_on(items) -> None:
    model = FakeModel()
    ask = _asker(model)

    def flaky(item):
        if item["id"] == "de-math-easy":
            raise TimeoutError("throttled")
        return ask(item)

    readings = evaluation.run(items, ask=flaky)
    summary = evaluation.summarize(readings)
    assert summary["errors"] == 1 and summary["replies"] == 40
    [failed] = [reading for reading in readings if reading.error]
    assert failed.item_id == "de-math-easy" and "TimeoutError" in failed.error


def test_a_paid_failure_is_still_costed(items) -> None:
    # A reply cut off at the token limit fails validation and is paid in full.
    from stoa.models.allowance import ProviderUsageEvidence

    usage = ProviderUsageEvidence.model_construct(input_tokens=800, output_tokens=2048)

    def truncated(_item):
        raise ai_service.AIInvocationFailure("output_truncated", usage=usage)

    summary = evaluation.summarize(evaluation.run(items[:1], ask=truncated))
    assert summary["errors"] == 1
    assert summary["tokens"] == {"input": 800, "output": 2048}


# --- The cost guard ---


def test_a_dry_run_calls_nothing(capsys) -> None:
    def never(_item):
        raise AssertionError("a dry run must not call the model")

    assert evaluation.main(["--dry-run"], asker=never) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["estimate"]["calls"] == 40


def test_a_paid_run_needs_its_cost_confirmed(capsys) -> None:
    def never(_item):
        raise AssertionError("an unconfirmed run must not call the model")

    assert evaluation.main([], asker=never) == 1
    assert "--confirm-cost" in capsys.readouterr().err


def test_even_a_dry_run_over_the_limit_is_refused(capsys) -> None:
    assert evaluation.main(["--dry-run", "--max-calls", "10"]) == 1
    assert "more than --max-calls 10" in capsys.readouterr().err


def test_no_sso_session_means_no_run(monkeypatch, capsys) -> None:
    from stoa.security import aws_operator_identity

    def refuse(**_kwargs):
        raise aws_operator_identity.AwsOperatorIdentityError("not an SSO operator session")

    monkeypatch.setattr(aws_operator_identity, "require_sso_operator_session", refuse)
    assert evaluation.main(["--confirm-cost", "--subset", "out-of-syllabus"]) == 1
    assert "not an SSO operator session" in capsys.readouterr().err


def test_more_calls_than_the_limit_are_refused(capsys) -> None:
    def never(_item):
        raise AssertionError("an over-limit run must not call the model")

    assert evaluation.main(["--confirm-cost", "--max-calls", "39"], asker=never) == 1
    assert "more than --max-calls 39" in capsys.readouterr().err


def test_a_confirmed_run_writes_its_report(tmp_path) -> None:
    status = evaluation.main(
        ["--confirm-cost", "--output-dir", str(tmp_path), "--label", "offline"],
        asker=_asker(FakeModel()),
    )
    assert status == 0
    report = json.loads((tmp_path / "ai-reply-eval-offline.json").read_text())
    assert report["summary"]["language_consistency_pct"] == 100.0
    assert len(report["replies"]) == 40
