"""The message command in two halves: commit it, then generate its answer (E19, #18).

Committing writes the student's message, the quota claim and the command, and
stores on the command what the request resolved for the answer - the language,
the subject, the grade, the student's weak topics. Generating reads only the
command, so it can later run somewhere without the request. Both halves still
run inside one request here, so the student sees what they saw before; what is
new is that the command ends in an explicit terminal state that
`GET /conversations/{id}/generation?idempotencyKey=` reports.

These run the real route and the real repository against the shared table
double. Only the model call and the entitlement lookup are replaced.
"""

from __future__ import annotations

import pytest

from fakes.ask_question import (
    charge_failures_as_paid,
    ANSWER,
    CONV,
    _client,
    _command_key,
    _command_row,
    _commit,
    _events,
    _generation,
    _messages,
    _send,
    default_language,
)
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.services import ai_service, ask_question, locale_service
from stoa.services.ask_question import _admission
from stoa.services.ask_question.errors import AskQuestionErrorCode


def test_a_committed_and_generated_answer_still_streams_as_before(table, model) -> None:
    client = _client()

    response = _send(client, "key-1")

    assert response.status_code == 200, response.text
    events = _events(response)
    assert [name for name, _ in events[:2]] == ["student_message", "message_start"]
    assert events[-1][0] == "message_done"
    streamed = "".join(data["delta"] for name, data in events if name == "message_delta")
    assert "So kürzt man." in streamed
    assert len(_messages(table, "assistant")) == 1
    assert len(_messages(table, "student")) == 1


def test_the_generation_endpoint_reports_the_completed_command(table, model) -> None:
    client = _client()
    _send(client, "key-1")

    generation = _generation(client, "key-1")

    [assistant] = _messages(table, "assistant")
    assert generation["status"] == "completed"
    assert generation["attempt"] == 1
    assert generation["assistantMessageId"] == assistant["message_id"]
    assert generation["failureCategory"] is None
    assert generation["commandId"] == _command_row(table, "key-1")["command_id"]
    assert generation["steps"] == ANSWER["steps"]
    assert generation["updatedAt"]


def test_the_command_carries_what_the_request_resolved_for_the_answer(table, model) -> None:
    _send(_client(), "key-1", language="fr")

    context = _command_row(table, "key-1")["generation_context"]
    assert context["locale"] == "fr"
    assert context["subject"] == "math"
    assert context["grade"] == "Grade 6"
    assert "memory_context" in context
    assert default_language(model, 0) == "fr"


def test_the_hint_is_labelled_in_the_language_the_model_answered_in(table, model) -> None:
    """The app shown in English, the question answered in German (#174)."""
    model.outcomes = [{**ANSWER, "hints": ["Such den ggT."], "language": "de"}]

    _send(_client(), "key-1", language="en")

    [assistant] = _messages(table, "assistant")
    assert assistant["content"].endswith("**Hinweis:** Such den ggT.")
    # The display language is still what the model was given as its default.
    assert default_language(model, 0) == "en"


def test_a_reply_without_a_language_is_labelled_in_the_display_language(table, model) -> None:
    model.outcomes = [{**ANSWER, "hints": ["Find the gcd."]}]

    _send(_client(), "key-1", language="en")

    [assistant] = _messages(table, "assistant")
    assert assistant["content"].endswith("**Hint:** Find the gcd.")


def test_generating_takes_the_language_from_the_command_not_the_request(
    table, model
) -> None:
    locale_service.set_request_locale("fr")
    _commit("key-1")
    assert _command_row(table, "key-1")["status"] == "message_committed"

    # Whatever request is around when the answer is generated no longer counts.
    locale_service.set_request_locale("en")
    outcome = ask_question.answer(CONV, "key-1")

    assert outcome == "completed"
    assert default_language(model) == "fr"
    assert _command_row(table, "key-1")["status"] == "completed"


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (ai_service.AIInvocationFailure("incomplete_output"), "incomplete_output"),
        (ai_service.AIInvocationFailure("malformed_response"), "malformed_response"),
        (ai_service.AIInvocationFailure("deadline_exceeded"), "deadline_exceeded"),
        (RuntimeError("provider went away"), "provider_error"),
    ],
)
def test_a_failed_answer_leaves_the_command_failed_with_its_category(
    table, model, failure, category
) -> None:
    client = _client()
    model.outcomes = [failure]

    response = _send(client, "key-1")

    assert response.status_code == 503
    assert _messages(table, "assistant") == []
    row = _command_row(table, "key-1")
    assert row["status"] == "failed"
    assert row["failure_category"] == category
    assert "leaseOwner" not in row
    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == category
    assert generation["retryable"] is True
    assert generation["assistantMessageId"] is None


def test_a_retry_with_the_same_key_resumes_the_same_command_after_an_unpaid_failure(
    table, model
) -> None:
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    assert _send(client, "key-1").status_code == 503

    retried = _send(client, "key-1")

    assert retried.status_code == 200, retried.text
    assert len(_messages(table, "student")) == 1
    assert len(_messages(table, "assistant")) == 1
    generation = _generation(client, "key-1")
    assert generation["status"] == "completed"
    assert generation["attempt"] == 2
    assert "failure_category" not in _command_row(table, "key-1")


def test_an_answer_refused_over_its_usage_evidence_is_not_generated_again(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model answered; only the accounting of it failed. Not a retry."""

    def refuse(*_a, **_k):
        raise _admission.AdmissionError(AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE)

    monkeypatch.setattr(
        _admission.UsageEvidence, "from_provider", classmethod(refuse)
    )
    client = _client()

    assert _send(client, "key-1").status_code == 503

    generation = _generation(client, "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "allowance_unavailable"
    assert generation["retryable"] is False


def test_a_failure_the_provider_charged_for_is_not_generated_again(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paid answer that could not be used is a known result, not a retry."""
    charge_failures_as_paid(monkeypatch)
    client = _client()
    model.outcomes = [ai_service.AIInvocationFailure("incomplete_output")]
    assert _send(client, "key-1").status_code == 503
    assert _generation(client, "key-1")["retryable"] is False

    retried = _send(client, "key-1")

    assert retried.status_code == 409, retried.text
    assert retried.json()["detail"]["code"] == "message_failed"
    assert len(model.calls) == 1
    assert _generation(client, "key-1")["status"] == "failed"


def test_steps_are_reported_only_for_the_command_that_wrote_them(table, model) -> None:
    client = _client()
    _send(client, "key-1")
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    _send(client, "key-2", content="Und wie erweitere ich?")

    assert _generation(client, "key-2")["steps"] == []
    assert _generation(client, "key-1")["steps"] == ANSWER["steps"]


def test_without_a_key_the_endpoint_answers_in_its_old_shape(table, model) -> None:
    client = _client()
    _send(client, "key-1")

    generation = _generation(client, None)

    assert generation["conversationId"] == CONV
    assert generation["steps"] == ANSWER["steps"]
    assert generation["updatedAt"]
    assert generation["status"] is None


def test_an_unknown_key_is_reported_as_an_unavailable_message(table, model) -> None:
    response = _client().get(f"/conversations/{CONV}/generation?idempotencyKey=nope")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "message_command_not_found"


def test_a_command_written_before_the_split_still_reads_and_resumes(
    table, model
) -> None:
    """In-flight commands of the previous version carry no generation context."""
    locale_service.set_request_locale("de")
    _commit("key-1")
    key = tuple(_command_key(CONV, "key-1").values())
    legacy = dict(table.rows[key])
    legacy.pop("generation_context")
    table.seed(legacy)
    client = _client()
    assert _generation(client, "key-1")["status"] == "message_committed"

    resumed = _send(client, "key-1", language="it")

    assert resumed.status_code == 200, resumed.text
    assert default_language(model) == "it"
    assert _generation(client, "key-1")["status"] == "completed"
    assert len(_messages(table, "student")) == 1


def test_an_old_running_command_reads_as_running(table, model) -> None:
    locale_service.set_request_locale("de")
    _commit("key-1")
    key = tuple(_command_key(CONV, "key-1").values())
    legacy = dict(table.rows[key])
    legacy.pop("generation_context")
    legacy.update(status="ai_running", attempt=1, leaseOwner="old", expiresAt=1)
    table.seed(legacy)

    generation = _generation(_client(), "key-1")

    assert generation["status"] == "ai_running"
    assert generation["attempt"] == 1


def test_the_same_key_after_success_replays_the_stored_answer(table, model) -> None:
    client = _client()
    first = _events(_send(client, "key-1"))

    second = _events(_send(client, "key-1"))

    assert first[1][1]["messageId"] == second[1][1]["messageId"]
    assert len(model.calls) == 1
    assert len(_messages(table, "assistant")) == 1
