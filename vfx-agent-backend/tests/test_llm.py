"""Shared LLM adapter tests."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from agent.llm import call_llm_structured


class SummaryOutput(BaseModel):
    summary: str


def test_compatible_endpoint_fallback_uses_requested_output_schema():
    model = MagicMock()
    model.invoke.return_value = AIMessage(content='{"summary": "A wrist glow."}')

    with patch("agent.llm.API_ENDPOINT", "https://compatible.example"), \
         patch("agent.llm.get_llm", return_value=model):
        result = call_llm_structured(
            model="test-model",
            system="Summarize.",
            user="Input",
            output_schema=SummaryOutput,
        )

    system_prompt = model.invoke.call_args.args[0][0].content
    assert result.summary == "A wrist glow."
    assert '"summary"' in system_prompt
    assert '"passed"' not in system_prompt
