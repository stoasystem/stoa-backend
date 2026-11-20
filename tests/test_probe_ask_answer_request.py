"""The probe of the Ask answer's request (#444), on the fake adapter."""

from __future__ import annotations

from scripts import probe_ask_answer_request as probe
from stoa.services import ask_answer, model_call
from stoa.services.model_call.adapter import ProviderError
from stoa.services.model_call.fake import FakeAdapter


def test_the_probed_bodies_are_the_ones_the_ask_answer_counts_and_sends() -> None:
    counted, sent = probe.ask_bodies()

    [tool] = sent["tools"]
    assert tool["name"] == ask_answer.ANSWER_TOOL_NAME
    # With the star map shown, so the tool carries every property it can.
    assert tool["input_schema"] == ask_answer.answer_tool(star_map=True).input_schema
    assert "common_mistakes" in tool["input_schema"]["properties"]
    assert tool["strict"] is True
    assert tool["eager_input_streaming"] is True
    unstreamed = {key: value for key, value in tool.items() if key != "eager_input_streaming"}
    assert counted == model_call._count_body(sent) == {**sent, "tools": [unstreamed]}
    # The synthetic exercise and its recent mistake ride in the student's turn.
    assert "<practice_context-" in sent["messages"][-1]["content"]
    assert "recentMistakes" in sent["messages"][-1]["content"]


def test_the_probe_leaves_no_adapter_of_its_own_installed() -> None:
    model = FakeAdapter()
    model_call.install(model)

    probe.ask_bodies()

    # Back to Bedrock: the probe's recorder is gone, the test's too.
    assert model_call._installed is None


def test_count_only_by_default_and_both_checks_pass_on_the_fake() -> None:
    model = FakeAdapter({"steps": ["x"], "answer": "y"})

    lines = probe.probe(model, model_id="eu.anthropic.claude-sonnet-4-6", invoke=False)

    assert lines[0].startswith("INFO tool give_answer with ")
    assert "common_mistakes" in lines[0]
    assert lines[1].startswith("PASS count:")
    assert lines[2].startswith("SKIP invoke:")
    assert model.counted == 1 and model.calls == []

    lines = probe.probe(model, model_id="eu.anthropic.claude-sonnet-4-6", invoke=True)

    assert lines[2].startswith("PASS invoke:")
    assert model.calls[-1]["max_tokens"] == 1


def test_a_refusal_is_reported_with_bedrock_s_own_words_and_fails_the_run() -> None:
    class Refusing(FakeAdapter):
        def count(self, model_id, body):
            raise ProviderError(
                "ValidationException", http_status=400, message="tools.0.custom.x: Extra inputs"
            )

    code = probe.main(["--model-id", "eu.anthropic.claude-sonnet-4-6"], adapter=Refusing())

    assert code == 1
