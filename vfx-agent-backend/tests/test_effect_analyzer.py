"""EffectAnalyzer contract tests for internal evidence and safe summaries."""

import threading

import pytest
from langchain_core.messages import AIMessage, SystemMessage
from unittest.mock import MagicMock, patch

from agent.effect_analyzer import (
    EffectAnalyzer,
    ReferenceAnalysisError,
    ReferenceSource,
)


SOURCE_CODE = """class Effect {
  display(sketch, frameData, params) {
    const wrist = frameData.joints.left_wrist;
    sketch.circle(wrist.x, wrist.y, params.size);
  }
}"""


def test_internal_evidence_must_be_an_exact_source_substring_and_retries_once():
    responses = [
        {
            "findings": [{
                "role": "wrist anchor",
                "evidence": "frameData.joints.right_wrist",
                "usage": "Reuse the wrist binding.",
            }],
        },
        {
            "findings": [{
                "role": "wrist anchor",
                "evidence": "frameData.joints.left_wrist",
                "usage": "Reuse only the wrist binding.",
            }],
        },
    ]
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs["user"])
        return kwargs["output_schema"].model_validate(responses.pop(0))

    analyzer = EffectAnalyzer(model="test-model", structured_call=fake_call)
    result = analyzer.analyze_evidence([
        ReferenceSource(
            effect_id="effect-1",
            code=SOURCE_CODE,
            reference_intent="Reuse only the wrist anchor.",
        )
    ])

    assert len(calls) == 2
    assert "exact substring" in calls[1]
    assert result[0].findings[0].evidence == "frameData.joints.left_wrist"


def test_invalid_evidence_after_one_retry_stops_generation():
    def fake_call(**kwargs):
        return kwargs["output_schema"].model_validate({
            "findings": [{
                "role": "invented",
                "evidence": "not present in source",
                "usage": "Reuse it.",
            }],
        })

    analyzer = EffectAnalyzer(model="test-model", structured_call=fake_call)

    with pytest.raises(ReferenceAnalysisError, match="exact source substring"):
        analyzer.analyze_evidence([
            ReferenceSource(
                effect_id="effect-1",
                code=SOURCE_CODE,
                reference_intent="Reuse the anchor.",
            )
        ])


def test_parallel_evidence_keeps_reference_order_and_fits_total_budget():
    lock = threading.Lock()
    seen_threads = set()

    def fake_call(**kwargs):
        with lock:
            seen_threads.add(threading.get_ident())
        code = kwargs["user"].split("SOURCE CODE:\n", 1)[1]
        evidence = code.splitlines()[0]
        return kwargs["output_schema"].model_validate({
            "findings": [
                {"role": "primary", "evidence": evidence, "usage": "Reuse it."},
                {"role": "secondary", "evidence": evidence, "usage": "Reuse it lightly."},
            ]
        })

    sources = [
        ReferenceSource(
            effect_id=f"effect-{index}",
            code=f"const anchor{index} = frameData.joints.left_wrist;\n// source {index}",
            reference_intent="Reuse the anchor.",
        )
        for index in range(3)
    ]
    analyzer = EffectAnalyzer(
        model="test-model",
        structured_call=fake_call,
        max_evidence_chars=150,
        concurrency=3,
    )

    result = analyzer.analyze_evidence(sources)

    assert [item.effect_id for item in result] == ["effect-0", "effect-1", "effect-2"]
    assert all(1 <= len(item.findings) <= 5 for item in result)
    assert sum(
        len(finding.evidence)
        for item in result
        for finding in item.findings
    ) <= 150


def test_budget_that_cannot_keep_one_excerpt_per_reference_asks_to_reduce():
    def fake_call(**kwargs):
        return kwargs["output_schema"].model_validate({
            "findings": [{
                "role": "anchor",
                "evidence": "left_wrist",
                "usage": "Reuse it.",
            }]
        })

    analyzer = EffectAnalyzer(
        model="test-model",
        structured_call=fake_call,
        max_evidence_chars=1,
    )
    sources = [
        ReferenceSource(
            effect_id=f"effect-{index}",
            code="left_wrist",
            reference_intent="Reuse the anchor.",
        )
        for index in range(2)
    ]

    with pytest.raises(ReferenceAnalysisError, match="reduce references"):
        analyzer.analyze_evidence(sources)


def test_safe_summary_retries_code_leak_and_returns_code_free_text():
    responses = [
        {"summary": "It calls sketch.circle(wrist.x, wrist.y, params.size);"},
        {"summary": "A compact glow follows the left wrist and expands with its control."},
    ]

    def fake_call(**kwargs):
        return kwargs["output_schema"].model_validate(responses.pop(0))

    analyzer = EffectAnalyzer(model="test-model", structured_call=fake_call)
    summary = analyzer.summarize(
        ReferenceSource(
            effect_id="effect-1",
            code=SOURCE_CODE,
            reference_intent="Explain how the effect moves.",
        )
    )

    assert summary.effect_id == "effect-1"
    assert summary.summary == (
        "A compact glow follows the left wrist and expands with its control."
    )
    assert "sketch." not in summary.summary
    assert not any(character.isdigit() for character in summary.summary)


@patch("agent.code_agent.get_code_agent_llm")
def test_code_agent_receives_only_validated_reference_evidence(mock_get_llm):
    from agent.code_agent import invoke_code_agent

    model = MagicMock()
    model.bind_tools.return_value = model
    model.invoke.return_value = AIMessage(content="No submission.")
    mock_get_llm.return_value = model
    evidence = [{
        "effect_id": "effect-1",
        "reference_intent": "Reuse only the wrist anchor.",
        "findings": [{
            "role": "wrist anchor",
            "evidence": "frameData.joints.left_wrist",
            "usage": "Reuse the same anchor choice.",
        }],
    }]

    result = invoke_code_agent(
        video_id="video-1",
        user_description="Create a new wrist glow.",
        reference_evidence=evidence,
    )

    messages = model.invoke.call_args.args[0]
    injected = [
        message.content
        for message in messages
        if isinstance(message, SystemMessage)
        and "INTERNAL SAVED-EFFECT EVIDENCE" in message.content
    ]
    assert len(injected) == 1
    assert "frameData.joints.left_wrist" in injected[0]
    assert SOURCE_CODE not in injected[0]
    assert result.injected_reference_ids == ["effect-1"]
