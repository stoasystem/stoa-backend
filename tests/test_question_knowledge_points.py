"""The old "submit a question" route shares the Ask prompt, but has no star map (#142).

Knowledge points are picked from the student's star map only on the Ask path,
which shows the model one. Here the model is asked for plain names, as before,
and a reply that names its points as `{id, name}` anyway is stored as names:
the question row, the learning history and the weekly report all read them as
text.

The real route, prompt builder and allowance wrapper run; only the Bedrock
provider and the question table are stood in for.
"""

from __future__ import annotations

import json

import pytest

from test_phase475_question_effect_recovery import EffectRecoveryTable, _client, _request
from test_question_token_finalization import MockBedrockProvider, _patch_allowance_runtime
from test_token_allowances import AtomicAllowanceTable


class _ProviderNamingObjects(MockBedrockProvider):
    """Answers the way the Ask prompt asks for, with `{id, name}` points."""

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        response = super().invoke_model(**kwargs)
        payload = json.loads(response["body"].read())
        content = json.loads(payload["content"][0]["text"])
        content["knowledge_points"] = [
            {"id": "k1", "name": "linear equations"},
            {"id": None, "name": "balancing both sides"},
            "isolating x",
            {"id": "k2"},
        ]
        payload["content"][0]["text"] = json.dumps(content)
        response["body"] = type(response["body"])(payload)
        return response


@pytest.fixture
def question_table() -> EffectRecoveryTable:
    return EffectRecoveryTable()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch, question_table) -> MockBedrockProvider:
    provider = _ProviderNamingObjects()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=AtomicAllowanceTable(),
        provider=provider,
    )
    return provider


def test_a_question_is_answered_with_its_points_as_names(provider) -> None:
    response = _client().post("/questions", json=_request())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["knowledge_points"] == [
        "linear equations",
        "balancing both sides",
        "isolating x",
    ]
    assert body["ai_response"]["knowledge_points"] == body["knowledge_points"]


def test_a_question_answered_on_recovery_keeps_its_points_as_names(
    provider, question_table
) -> None:
    """The answer generated when a replay finds the first attempt's intent missing."""
    question_table.fail_intent_before_commit = 1

    first = _client().post("/questions", json=_request())
    second = _client().post("/questions", json=_request())

    assert first.status_code == 201 and first.json()["status"] == "pending"
    assert second.status_code == 201, second.text
    assert second.json()["status"] == "ai_answered"
    assert second.json()["knowledge_points"] == [
        "linear equations",
        "balancing both sides",
        "isolating x",
    ]


def test_the_question_route_asks_for_plain_names(provider) -> None:
    _client().post("/questions", json=_request())

    [call] = provider.invoke_calls
    system = json.loads(str(call["body"]))["system"]
    assert '"knowledge_points":["..."]' in system
    assert "star map" not in system
