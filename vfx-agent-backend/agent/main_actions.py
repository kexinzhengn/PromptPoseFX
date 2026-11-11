"""Model-visible MainAgent actions and strict response parsing."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from .schemas import (
    ClarificationOption,
    ClarifyAction,
    DiscardReferencesAction,
    GenerateAction,
    InspectEffectsAction,
    ParameterValue,
    ReferenceRequest,
    ReferenceQuery,
    ResolveReferencesAction,
    RespondAction,
    UpdateEffectAction,
)


@tool
def ask_clarification(
    question: str,
    options: list[ClarificationOption],
) -> str:
    """Ask one high-impact question with complete executable options."""
    return "Action accepted."


@tool
def generate_effect(
    user_description: str,
    requested_name: str | None = None,
    references: list[ReferenceRequest] | None = None,
    parameter_updates: dict[str, ParameterValue] | None = None,
) -> str:
    """Generate or structurally modify the current Effect from an English brief."""
    return "Action accepted."


@tool
def update_effect(
    requested_name: str | None = None,
    parameter_updates: dict[str, ParameterValue] | None = None,
) -> str:
    """Update only the current Effect name or existing CONFIG parameter values."""
    return "Action accepted."


@tool
def inspect_effects(effect_ids: list[str], question: str) -> str:
    """Read code-free metadata for explicitly identified active Effects."""
    return "Action accepted."


@tool
def resolve_references(queries: list[ReferenceQuery]) -> str:
    """Find historical Effects by name, description or conversational reference."""
    return "Action accepted."


@tool
def discard_reference_request() -> str:
    """Clear the pending reference request when the user cancels or starts a different task."""
    return "Action accepted."


MAIN_AGENT_TOOLS = [
    resolve_references,
    ask_clarification,
    generate_effect,
    update_effect,
    inspect_effects,
    discard_reference_request,
]


_ACTION_MODELS = {
    "discard_reference_request": (DiscardReferencesAction, "discard_reference_request"),
    "resolve_references": (ResolveReferencesAction, "resolve_references"),
    "ask_clarification": (ClarifyAction, "clarify"),
    "generate_effect": (GenerateAction, "generate"),
    "update_effect": (UpdateEffectAction, "update_effect"),
    "inspect_effects": (InspectEffectsAction, "inspect_effects"),
}


def parse_main_action(message: AIMessage):
    """Convert exactly one model response into a typed MainAgent action."""
    tool_calls = message.tool_calls or []
    if tool_calls:
        if len(tool_calls) != 1:
            raise ValueError("MainAgent must return exactly one action")
        tool_call = tool_calls[0]
        action_spec = _ACTION_MODELS.get(tool_call.get("name", ""))
        if action_spec is None:
            raise ValueError(f"Unknown MainAgent action: {tool_call.get('name', '')}")
        model, discriminator = action_spec
        payload: dict[str, Any] = {
            "action": discriminator,
            **tool_call.get("args", {}),
        }
        return model.model_validate(payload)

    content = message.content
    if not isinstance(content, str) or not content.strip():
        raise ValueError("MainAgent must return exactly one action")
    return RespondAction(message=content.strip())
