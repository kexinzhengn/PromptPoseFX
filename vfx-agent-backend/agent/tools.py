import json

from langchain_core.tools import tool
from config import MAX_OUTER_RETRIES
from . import code_agent as code_agent_module
from .extract_config import extract_config
from .events import get_callback


@tool
def invoke_code_agent(
    user_description: str,
    prev_code: str = "",
    effect_name: str = "",
    video_id: str = "",   # Injected from graph state; hidden from the model.
    reference_evidence: list[dict] | None = None,  # Verified saved-Effect excerpts.
    editor_context: dict | None = None,  # Trusted controls fixed before this run.
    required_control_ids: list[str] | None = None,  # Injected from raw user input.
) -> dict:
    """
    Generate or modify effect code with CodeAgent.

    Runs the CodeAgent plan, implementation, validation, and submission loop. On failure,
    this tool performs at most MAX_OUTER_RETRIES retries. Each retry starts from the original
    request plus only the latest failure reason and repairs last_validated_code when available.

    Args:
        user_description: Clear, complete natural-language requirement.
        prev_code: Existing effect code for edits, empty for new effects.
        effect_name: Effect name chosen by MainAgent after clarifying the request.
        video_id: Video ID injected by the system.

    Returns:
        {
            "status": "submitted" | "failed",
            "code": submitted code or an empty string,
            "params": defaults extracted from CONFIG,
            "effect_name": effect name,
            "reason": final failure reason or an empty string,
            "last_validated_code": latest validated code for draft fallback,
        }
    """
    code_kwargs = {
        "video_id": video_id,
        "user_description": user_description,
        "prev_code": prev_code,
    }
    if reference_evidence:
        code_kwargs["reference_evidence"] = reference_evidence
    if editor_context:
        code_kwargs["editor_context"] = editor_context
    if required_control_ids is not None:
        code_kwargs["required_control_ids"] = required_control_ids

    result = code_agent_module.invoke_code_agent(**code_kwargs)

    retry_count = 0
    while result.status == "failed" and retry_count < MAX_OUTER_RETRIES:
        retry_count += 1
        print(f"  [Tool] CodeAgent retry {retry_count}/{MAX_OUTER_RETRIES}: {result.reason}")
        cb = get_callback()
        if cb:
            cb({"type": "retry", "attempt": retry_count, "max": MAX_OUTER_RETRIES, "reason": result.reason})
        code_kwargs["user_description"] = _with_failure_reason(user_description, result.reason)
        code_kwargs["prev_code"] = result.last_validated_code or prev_code
        result = code_agent_module.invoke_code_agent(**code_kwargs)

    code = result.code

    # Extract default parameters from static CONFIG.
    success, params_json = extract_config(code)
    params = json.loads(params_json) if success else {}

    return {
        "status": result.status,
        "code": code,
        "params": params,
        "effect_name": effect_name,
        "reason": result.reason,
        "last_validated_code": result.last_validated_code,
        "injected_reference_ids": result.injected_reference_ids or [],
    }


def _with_failure_reason(original: str, reason: str) -> str:
    """Append only the latest failure reason to the original request."""
    return f"{original}\n\n[Latest failure reason] {reason}"
