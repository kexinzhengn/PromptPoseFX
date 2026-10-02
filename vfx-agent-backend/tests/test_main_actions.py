"""MainAgent action schema and model-visible tool boundary tests."""

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from agent.main_actions import MAIN_AGENT_TOOLS, parse_main_action
from agent.schemas import ClarifyAction, GenerateAction, RespondAction


def test_main_agent_tools_expose_only_supported_product_actions():
    assert [tool.name for tool in MAIN_AGENT_TOOLS] == [
        "ask_clarification",
        "generate_effect",
        "update_effect",
        "inspect_effects",
    ]


def test_plain_response_becomes_respond_action():
    action = parse_main_action(AIMessage(content="PromptPoseFX uses pose joints, not image pixels."))

    assert isinstance(action, RespondAction)
    assert action.message == "PromptPoseFX uses pose joints, not image pixels."


def test_generate_tool_call_becomes_typed_action_without_technical_inputs():
    action = parse_main_action(AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Create a violet glow around the left wrist.",
            "requested_name": "Violet Wrist Glow",
            "references": [],
            "parameter_updates": {"strength": 4},
        },
        "id": "call-1",
    }]))

    assert isinstance(action, GenerateAction)
    assert action.user_description.startswith("Create a violet glow")
    tool_schema = next(tool for tool in MAIN_AGENT_TOOLS if tool.name == "generate_effect").args
    assert "video_id" not in tool_schema
    assert "prev_code" not in tool_schema
    assert "reference_evidence" not in tool_schema


def test_clarification_options_store_complete_generation_briefs():
    action = parse_main_action(AIMessage(content="", tool_calls=[{
        "name": "ask_clarification",
        "args": {
            "question": "Which direction should the energy take?",
            "options": [
                {
                    "label": "Orbiting rings",
                    "description": "Two rings orbit both wrists.",
                    "brief": {
                        "user_description": "Create two cyan rings orbiting both wrists.",
                        "requested_name": "Orbiting Wrist Rings",
                    },
                },
                {
                    "label": "Rising stream",
                    "description": "Energy rises from both wrists.",
                    "brief": {
                        "user_description": "Create cyan energy rising from both wrists.",
                        "requested_name": "Rising Wrist Energy",
                    },
                },
            ],
        },
        "id": "call-2",
    }]))

    assert isinstance(action, ClarifyAction)
    assert action.options[0].brief.requested_name == "Orbiting Wrist Rings"


def test_multiple_or_unknown_actions_are_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        parse_main_action(AIMessage(content="", tool_calls=[
            {"name": "generate_effect", "args": {"user_description": "A"}, "id": "a"},
            {"name": "update_effect", "args": {"requested_name": "B"}, "id": "b"},
        ]))

    with pytest.raises(ValueError, match="Unknown MainAgent action"):
        parse_main_action(AIMessage(content="", tool_calls=[{
            "name": "invoke_code_agent",
            "args": {"user_description": "A"},
            "id": "legacy",
        }]))

    with pytest.raises(ValidationError):
        parse_main_action(AIMessage(content="", tool_calls=[{
            "name": "generate_effect",
            "args": {"video_id": "forbidden"},
            "id": "invalid",
        }]))
