import json
import os
import re
import threading
import time
import uuid

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from .schemas import AgentState
from .tools import invoke_code_agent
from editor_controls import resolve_required_control_ids
from .main_actions import MAIN_AGENT_TOOLS, parse_main_action
from .schemas import MainAgentAction
from .effect_analyzer import EffectAnalyzer, ReferenceAnalysisError, ReferenceSource
from .prompts import MAIN_AGENT_SYSTEM
from .extract_config import extract_config_labels_and_descriptions
from .config_contract import validate_static_config
from . import events as agent_events
from config import CHECKPOINT_DB
from chat_manager import ChatManager
from effect_repository import (
    EffectEditorStateError,
    EffectNotFoundError,
    EffectParameterError,
)
from pydantic import TypeAdapter, ValidationError

_chat_manager = ChatManager()

# Thread-local progress callbacks shared between LangGraph nodes.
# process_user_message sets the callback and _tool_node reads it safely.
_thread_local = threading.local()

_MAIN_SYSTEM_MESSAGE_ID = "main-agent-system-v2"
_TRUSTED_CONTEXT_MESSAGE_ID = "main-agent-trusted-context-v2"
_CHECKPOINT_NAMESPACE = "main-agent-v2"


# ====== Graph construction ======

def build_main_agent_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", _tool_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", _should_continue)
    builder.add_conditional_edges("tools", _after_action)
    return builder.compile(checkpointer=checkpointer)


_main_graph = None


def _build_checkpointer():
    """Build the SQLite checkpointer used for persistent LangGraph thread state."""
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    os.makedirs(os.path.dirname(CHECKPOINT_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    return SqliteSaver(conn)


def _get_main_graph():
    """Reuse one MainAgent graph with persistent SQLite checkpoints."""
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_agent_graph(checkpointer=_build_checkpointer())
    return _main_graph


def _thread_exists(graph, thread_id: str) -> bool:
    """Return whether a thread checkpoint already exists for a continued conversation."""
    return graph.checkpointer.get_tuple({"configurable": {"thread_id": thread_id}}) is not None


def _checkpoint_thread_id(workspace_id: str) -> str:
    """Keep V2 checkpoints isolated from legacy messages and prompts."""
    return f"{_CHECKPOINT_NAMESPACE}:{workspace_id}"


def _agent_node(state: AgentState):
    from .llm import get_main_agent_llm
    forced_action = state.get("forced_action") or {}
    if forced_action:
        action = TypeAdapter(MainAgentAction).validate_python(forced_action)
        semantic_error = _action_semantic_error(action.model_dump(), state)
        if semantic_error:
            message = (
                "I could not safely preserve the selected editor controls. "
                "Please describe the Effect again using the visible pN/pathN/tN aliases."
            )
            return {
                "messages": [AIMessage(content=message)],
                "main_action": {"action": "respond", "message": message},
                "action_name": "respond",
                "action_error": "control_alias_lost",
                "forced_action": {},
            }
        response = _action_to_message(action.model_dump())
        return {
            "messages": [response],
            "main_action": action.model_dump(),
            "action_name": action.action,
            "action_error": "",
            "forced_action": {},
        }

    llm = get_main_agent_llm().bind_tools(MAIN_AGENT_TOOLS)
    t0 = time.time()
    response = llm.invoke(state["messages"])
    try:
        action = parse_main_action(response)
        semantic_error = _action_semantic_error(action.model_dump(), state)
        if semantic_error:
            raise ValueError(semantic_error)
    except (ValueError, ValidationError) as first_error:
        repair_message = SystemMessage(
            content=(
                "Your previous MainAgent action was invalid. Return exactly one valid action. "
                "When the trusted operation is create, every generation brief must include a concise, non-empty English requested_name. "
                "You must preserve existing editor control aliases in every generation brief; "
                "never redefine a listed pN/pathN/tN alias as another control, playhead frame, Pose event, or motion trigger. "
                f"Validation error: {_short_error(first_error)}"
            )
        )
        response = llm.invoke([*state["messages"], repair_message])
        try:
            action = parse_main_action(response)
            semantic_error = _action_semantic_error(action.model_dump(), state)
            if semantic_error:
                raise ValueError(semantic_error)
        except (ValueError, ValidationError) as second_error:
            message = (
                "I could not safely interpret this request. "
                "Please rephrase it with the target body area and intended visual behavior."
            )
            print(f"  [MainAgent] Invalid action after repair: {_short_error(second_error)}")
            return {
                "messages": [AIMessage(content=message)],
                "main_action": {"action": "respond", "message": message},
                "action_name": "respond",
                "action_error": "invalid_action",
            }

    elapsed = time.time() - t0
    print(f"  [MainAgent] Action {action.action} ({elapsed:.1f}s)")
    return {
        "messages": [response],
        "main_action": action.model_dump(),
        "action_name": action.action,
        "action_error": "",
    }


def _tool_node(state: AgentState):
    action = state.get("main_action", {})
    action_name = action.get("action", "")
    state_updates: dict = {"action_result": {}}
    safe_result = {"status": "completed"}

    if action_name == "generate":
        reference_evidence = []
        references = action.get("references", [])
        if references:
            allowed_ids = _authorized_reference_ids(state)
            if any(item.get("effect_id") not in allowed_ids for item in references):
                state_updates["action_error"] = "reference_not_authorized"
                safe_result = {"status": "rejected"}
            else:
                sources = []
                for item in references:
                    detail = _chat_manager.get_effect_detail(item["effect_id"])
                    if detail is None or detail.get("status") != "active":
                        state_updates["action_error"] = "reference_not_authorized"
                        safe_result = {"status": "rejected"}
                        break
                    sources.append(ReferenceSource(
                        effect_id=item["effect_id"],
                        code=detail["code"],
                        reference_intent=item["reference_intent"],
                    ))
                if not state_updates.get("action_error"):
                    try:
                        reference_evidence = [
                            item.model_dump()
                            for item in EffectAnalyzer().analyze_evidence(sources)
                        ]
                    except ReferenceAnalysisError:
                        state_updates["action_error"] = "reference_analysis_failed"
                        safe_result = {"status": "rejected"}

        if not state_updates.get("action_error"):
            cb = getattr(_thread_local, "progress_callback", None)
            if cb:
                cb("generating", "Generating effect code...")
            editor_context = state.get("editor_context", {})
            description = action["user_description"]
            if not editor_context:
                description = _expand_pinned_joint_aliases(
                    description,
                    state.get("pinned_joints", {}),
                )
            tool_args = {
                "video_id": state.get("video_id", ""),
                "user_description": description,
                "effect_name": action.get("requested_name")
                or state.get("effect_name")
                or "Untitled Effect",
                "prev_code": state.get("prev_code", "")
                if state.get("operation") == "edit"
                else "",
            }
            if editor_context:
                tool_args["editor_context"] = editor_context
                required_control_ids = set(state.get("required_control_ids", []))
                required_control_ids.update(resolve_required_control_ids(
                    "\n".join([state.get("user_input", ""), description]),
                    editor_context,
                ))
                tool_args["required_control_ids"] = sorted(required_control_ids)
            if reference_evidence:
                tool_args["reference_evidence"] = reference_evidence
            result = invoke_code_agent.invoke(tool_args)
            state_updates.update({
                "code_status": result.get("status", ""),
                "failure_reason": result.get("reason", ""),
                "last_validated_code": result.get("last_validated_code", ""),
                "injected_reference_ids": result.get("injected_reference_ids", []),
                "effect_name": result.get("effect_name", tool_args["effect_name"]),
                "explicit_parameter_updates": action.get("parameter_updates", {}),
            })
            if result.get("code"):
                state_updates["code"] = result["code"]
                state_updates["params"] = json.dumps(result.get("params", {}), ensure_ascii=False)
            safe_result = {"status": result.get("status", "failed")}

    elif action_name == "update_effect":
        if state.get("operation") != "edit":
            state_updates["action_error"] = "no_editable_effect"
            safe_result = {"status": "rejected"}
        elif action.get("requested_name") is None and not action.get("parameter_updates"):
            state_updates["action_error"] = "empty_update"
            safe_result = {"status": "rejected"}
        else:
            try:
                detail = _chat_manager.patch_effect(
                    state["effect_id"],
                    effect_name=action.get("requested_name"),
                    parameter_updates=action.get("parameter_updates", {}),
                )
                state_updates["action_result"] = {
                    "effect_update": {
                        "effect_id": detail["effect_id"],
                        "name": detail["name"],
                        "params": detail["params"],
                        "parameter_ranges": detail["parameter_ranges"],
                        "status": detail["status"],
                    }
                }
            except (EffectNotFoundError, EffectParameterError) as error:
                state_updates["action_error"] = str(error)
                safe_result = {"status": "rejected"}

    elif action_name == "clarify":
        pending_options = {}
        visible_options = []
        allowed_ids = _authorized_reference_ids(state)
        unauthorized = any(
            reference.get("effect_id") not in allowed_ids
            for option in action.get("options", [])
            for reference in option.get("brief", {}).get("references", [])
        )
        if unauthorized:
            state_updates["action_error"] = "reference_not_authorized"
            safe_result = {"status": "rejected"}
        else:
            for option in action.get("options", []):
                option_id = uuid.uuid4().hex
                pending_options[option_id] = {
                    "action_payload": {
                        "action": "generate",
                        **option["brief"],
                    },
                    "required_control_ids": state.get("required_control_ids", []),
                }
                visible_options.append({
                    "id": option_id,
                    "label": option["label"],
                    "description": option["description"],
                })
            state_updates["pending_options"] = pending_options
            state_updates["action_result"] = {
                "question": action["question"],
                "options": visible_options,
            }

    elif action_name == "inspect_effects":
        allowed_ids = {
            effect["id"]
            for effect in state.get("effect_list", [])
            if effect.get("status") == "active"
        }
        summaries = []
        sources = []
        metadata_by_id = {}
        for effect_id in action.get("effect_ids", []):
            if effect_id not in allowed_ids:
                continue
            detail = _chat_manager.get_effect_detail(effect_id)
            if detail is not None:
                metadata_by_id[effect_id] = {
                    "effect_id": effect_id,
                    "name": detail["name"],
                }
                sources.append(ReferenceSource(
                    effect_id=effect_id,
                    code=detail["code"],
                    reference_intent=action.get("question", "Explain this Effect."),
                ))
        try:
            safe_summaries = EffectAnalyzer().summarize_many(sources)
            for summary in safe_summaries:
                summaries.append({
                    **metadata_by_id[summary.effect_id],
                    "summary": summary.summary,
                })
        except ReferenceAnalysisError:
            state_updates["action_error"] = "reference_analysis_failed"
            safe_result = {"status": "rejected"}
        state_updates["inspection_count"] = state.get("inspection_count", 0) + 1
        state_updates["action_result"] = {"inspection": summaries}
        if not state_updates.get("action_error"):
            safe_result = {"effects": summaries}

    last_message = state["messages"][-1]
    tool_call_id = last_message.tool_calls[0]["id"]
    return {
        "messages": [ToolMessage(content=json.dumps(safe_result), tool_call_id=tool_call_id)],
        **state_updates,
    }


def _should_continue(state: AgentState) -> str:
    if state.get("action_name") in {
        "clarify", "generate", "update_effect", "inspect_effects"
    }:
        return "tools"
    return END


def _after_action(state: AgentState) -> str:
    if (
        state.get("action_name") == "inspect_effects"
        and state.get("inspection_count", 0) <= 1
        and not state.get("action_error")
    ):
        return "agent"
    return END


def _short_error(error: Exception) -> str:
    return " ".join(str(error).split())[:500]


def _contains_alias(text: str, alias: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _required_control_aliases(state: AgentState) -> list[str]:
    required_ids = set(state.get("required_control_ids", []))
    editor_state = state.get("editor_context", {}).get("editor_state", {})
    controls = [
        *editor_state.get("points", []),
        *editor_state.get("paths", []),
        *editor_state.get("markers", []),
    ]
    return [
        control.get("alias", "")
        for control in controls
        if control.get("id") in required_ids and control.get("alias")
    ]


def _control_alias_error(action: dict, state: AgentState) -> str | None:
    """Reject generation briefs that drop explicitly referenced editor controls."""
    aliases = _required_control_aliases(state)
    if not aliases:
        return None
    action_name = action.get("action")
    if action_name == "generate":
        descriptions = [action.get("user_description", "")]
    elif action_name == "clarify":
        descriptions = [
            option.get("brief", {}).get("user_description", "")
            for option in action.get("options", [])
        ]
    else:
        return None
    missing = [
        alias
        for alias in aliases
        if any(not _contains_alias(description, alias) for description in descriptions)
    ]
    if not missing:
        return None
    return (
        "Existing editor control aliases were dropped from a generation brief: "
        + ", ".join(missing)
    )


def _action_semantic_error(action: dict, state: AgentState) -> str | None:
    """Validate context-dependent action rules that Pydantic cannot express."""
    if state.get("operation") == "create":
        action_name = action.get("action")
        if action_name == "generate":
            names = [action.get("requested_name")]
        elif action_name == "clarify":
            names = [
                option.get("brief", {}).get("requested_name")
                for option in action.get("options", [])
            ]
        else:
            names = []
        if any(not isinstance(name, str) or not name.strip() for name in names):
            return "A new Effect requires a non-empty requested_name in every generation brief"
    return _control_alias_error(action, state)


def _has_explicit_reference_request(user_input: str) -> bool:
    """Recognize language that explicitly asks to reuse a historical Effect."""
    pattern = re.compile(
        "\u53c2\u8003|\u501f\u9274|\u4eff\u7167|\u7c7b\u4f3c\u4e8e|\u50cf|"
        r"\b(?:reference|inspired\s+by|based\s+on)\b|"
        r"\blike\b.*\beffect\b",
        flags=re.IGNORECASE,
    )
    return bool(pattern.search(user_input))


def _authorized_reference_ids(state: AgentState) -> set[str]:
    """Return active historical Effects authorized for this user turn."""
    allowed_ids = {
        mention.get("effect_id", "")
        for mention in state.get("effect_mentions", [])
        if mention.get("effect_id")
    }
    if _has_explicit_reference_request(state.get("user_input", "")):
        allowed_ids.update(
            effect.get("id", "")
            for effect in state.get("effect_list", [])
            if effect.get("status") == "active"
            and effect.get("id") != state.get("effect_id")
        )
    return allowed_ids


def _action_to_message(action: dict) -> AIMessage:
    action_name = action["action"]
    tool_names = {
        "clarify": "ask_clarification",
        "generate": "generate_effect",
        "update_effect": "update_effect",
        "inspect_effects": "inspect_effects",
    }
    if action_name == "respond":
        return AIMessage(content=action["message"])
    args = {key: value for key, value in action.items() if key != "action"}
    return AIMessage(content="", tool_calls=[{
        "name": tool_names[action_name],
        "args": args,
        "id": f"forced-{uuid.uuid4().hex}",
    }])


def _build_trusted_context(
    operation: str,
    detail: dict | None,
    effect_list: list[dict],
    pinned_joints: dict[str, str],
    effect_mentions: list[dict],
    editor_context: dict | None = None,
) -> str:
    """Build code-free editor context owned by the backend."""
    lines = ["## Trusted editor context", f"[Operation: {operation}]"]

    if operation == "edit" and detail:
        lines.append(
            "[Current effect: "
            f"name={detail.get('name', '')}; status={detail.get('status', 'active')}]"
        )
        config, errors = validate_static_config(detail.get("code", ""))
        if not errors:
            params = detail.get("params", {})
            controls = {}
            for key, metadata in config.items():
                controls[key] = {
                    field: value
                    for field, value in metadata.items()
                    if field in {
                        "type", "label", "description", "default",
                        "min", "max", "step", "options",
                    }
                }
                controls[key]["current"] = params.get(key, metadata.get("default"))
            lines.append(
                "[Current controls: "
                + json.dumps(controls, ensure_ascii=False, sort_keys=True)
                + "]"
            )

    active_effects = [effect for effect in effect_list if effect.get("status") == "active"]
    if active_effects:
        summaries = [
            {
                "id": effect.get("id", ""),
                "name": effect.get("name", ""),
                "updated_at": effect.get("updated_at", ""),
            }
            for effect in active_effects
        ]
        lines.append(
            "[Active effects: "
            + json.dumps(summaries, ensure_ascii=False, sort_keys=True)
            + "]"
        )
    else:
        lines.append("[No active effects]")

    if pinned_joints:
        lines.append(
            "[Pinned joints: "
            + json.dumps(pinned_joints, ensure_ascii=False, sort_keys=True)
            + "]"
        )
    else:
        lines.append("[No pinned joints]")

    if editor_context:
        editor_state = editor_context.get("editor_state", {})
        active_interval = editor_state.get("active_interval", {})
        lines.append(
            "[Effect clip: "
            + json.dumps(active_interval, ensure_ascii=False, sort_keys=True)
            + "]"
        )
        points = []
        points_by_id = {}
        for point in editor_state.get("points", []):
            source = point.get("source", {})
            summary = {
                "id": point.get("id", ""),
                "alias": point.get("alias", ""),
                "source_type": source.get("type", ""),
            }
            if source.get("type") == "joint":
                summary["joint"] = source.get("joint", "")
            points.append(summary)
            points_by_id[summary["id"]] = summary
        lines.append(
            "[Editor points: "
            + json.dumps(points, ensure_ascii=False, sort_keys=True)
            + "]"
        )
        paths = [
            {
                "id": path.get("id", ""),
                "alias": path.get("alias", ""),
                "point_count": len(path.get("points", [])),
            }
            for path in editor_state.get("paths", [])
        ]
        paths_by_id = {path["id"]: path for path in paths}
        lines.append(
            "[Editor paths: "
            + json.dumps(paths, ensure_ascii=False, sort_keys=True)
            + "]"
        )
        markers = [
            {
                "id": marker.get("id", ""),
                "alias": marker.get("alias", ""),
            }
            for marker in editor_state.get("markers", [])
        ]
        lines.append(
            "[Editor time markers: "
            + json.dumps(markers, ensure_ascii=False, sort_keys=True)
            + "]"
        )
        selection = editor_context.get("selection", {})
        selected_point = points_by_id.get(selection.get("selected_point_id"))
        selected_path = paths_by_id.get(selection.get("selected_path_id"))
        lines.append(
            "[Editor selection: "
            + json.dumps({
                "current_frame": selection.get("current_frame"),
                "selected_point": selected_point,
                "selected_path": selected_path,
            }, ensure_ascii=False, sort_keys=True)
            + "]"
        )
    else:
        lines.append("[No editor controls]")

    if effect_mentions:
        lines.append(
            "[Effect mentions: "
            + json.dumps(effect_mentions, ensure_ascii=False, sort_keys=True)
            + "]"
        )
    else:
        lines.append("[No effect mentions]")

    return "\n".join(lines)


def _expand_pinned_joint_aliases(
    description: str,
    pinned_joints: dict[str, str],
) -> str:
    """Compile trusted editor pin aliases into real Pose joint names."""
    compiled = description
    for alias, joint_name in sorted(
        pinned_joints.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        compiled = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])",
            joint_name,
            compiled,
            flags=re.IGNORECASE,
        )
    return compiled


def _resolve_effect_mentions(
    mentions: list[dict],
    effect_list: list[dict],
    current_effect_id: str,
    user_input: str = "",
) -> list[dict]:
    """Resolve frontend mention IDs against active backend metadata."""
    active_by_id = {
        effect.get("id"): effect
        for effect in effect_list
        if effect.get("status") == "active" and effect.get("id") != current_effect_id
    }
    resolved = []
    seen = set()
    for mention in mentions:
        effect_id = mention.get("effect_id", "") if isinstance(mention, dict) else ""
        effect = active_by_id.get(effect_id)
        if effect is None or effect_id in seen:
            continue
        seen.add(effect_id)
        resolved.append({"effect_id": effect_id, "display_name": effect.get("name", "")})

    previous_pattern = re.compile(
        "(?:\u4e0a\u4e00\u4e2a|\u4e0a\u4e00\u500b|"
        "\u524d\u4e00\u4e2a|\u524d\u4e00\u500b)"
        r"\s*(?:\u6548\u679c|\u7279\u6548)|\b(?:previous|last)\s+effect\b",
        flags=re.IGNORECASE,
    )
    if previous_pattern.search(user_input):
        previous_candidates = list(active_by_id.values())
        if previous_candidates:
            latest = max(
                previous_candidates,
                key=lambda effect: effect.get("updated_at", ""),
            )
            latest_id = latest.get("id", "")
            if latest_id and latest_id not in seen:
                resolved.append({
                    "effect_id": latest_id,
                    "display_name": latest.get("name", ""),
                })
    return resolved


# ====== Entry point ======

def process_user_message(
    video_id: str,
    user_input: str,
    effect_id: str,
    effect_messages: list[dict],
    prev_code: str,
    effect_name: str,
    effect_list: list[dict],
    pinned_joints: dict[str, str] | None = None,
    effect_mentions: list[dict] | None = None,
    selected_option_id: str | None = None,
    editor_context=None,
    progress_callback=None,  # (stage: str, content: str) -> None
    thread_id: str = "",     # Conversation thread ID; the backend creates the first one.
    event_callback=None,     # Structured tool and retry event callback.
    cancel_event=None,       # threading.Event cancellation signal.
    resume_checkpoint_id: str = "",  # Historical checkpoint used after cancellation rollback.
) -> dict:
    """
    Process one frontend conversation turn through MainAgent.

    Args:
        video_id: Video ID.
        user_input: User message for this turn.
        effect_id: Current effect ID, empty for a new effect.
        effect_messages: Current effect conversation history.
        prev_code: Existing code supplied for an edit.
        effect_name: Current effect name.
        effect_list: Summaries of all effects.

    Returns:
        {
            "response": str,            # User response without options markup.
            "options": list|None,       # Structured options [{label, description}].
            "options_header": str|None, # Question shown above the options.
            "effect_messages": [...],   # Updated conversation history.
            "new_effect": dict|None,    # Newly generated effect, if any.
        }
    """
    # One stable workspace ID covers pending work, retries, and the saved Effect.
    workspace_id = thread_id or effect_id or str(uuid.uuid4())
    thread_id = workspace_id
    effect_id = workspace_id
    pinned_joints = pinned_joints or {}
    effect_mentions = effect_mentions or []
    serialized_editor_context = (
        editor_context.model_dump(mode="json")
        if editor_context is not None
        else {}
    )
    required_control_ids = resolve_required_control_ids(
        user_input,
        serialized_editor_context,
    )

    # Storage decides create versus edit. Frontend copies are never authoritative.
    detail = _chat_manager.get_effect_detail(workspace_id)
    operation = "edit" if detail and detail.get("code") else "create"
    if operation == "edit":
        prev_code = detail.get("code", "")
        effect_name = detail.get("name", "")
    else:
        prev_code = ""
        effect_name = ""
    generation_base_name = effect_name
    effect_list = _chat_manager.get_effect_list()
    effect_mentions = _resolve_effect_mentions(
        effect_mentions,
        effect_list,
        workspace_id,
        user_input,
    )
    trusted_context = _build_trusted_context(
        operation=operation,
        detail=detail,
        effect_list=effect_list,
        pinned_joints=pinned_joints,
        effect_mentions=effect_mentions,
        editor_context=serialized_editor_context,
    )
    context_message = SystemMessage(
        content=trusted_context,
        id=_TRUSTED_CONTEXT_MESSAGE_ID,
    )

    # Restore existing threads from checkpoints; create a thread for the first message.
    graph = _get_main_graph()
    checkpoint_thread_id = _checkpoint_thread_id(workspace_id)
    checkpoint_config = {"configurable": {"thread_id": checkpoint_thread_id}}
    forced_action = {}
    if selected_option_id:
        snapshot = graph.get_state(checkpoint_config)
        pending_options = snapshot.values.get("pending_options", {}) if snapshot.values else {}
        pending_option = pending_options.get(selected_option_id, {})
        if not pending_option:
            response_message = (
                "That option is no longer available. Please choose or describe a new idea."
            )
            display_messages = _chat_manager.get_conversation(workspace_id)
            display_messages.extend([
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": response_message, "isError": True},
            ])
            _chat_manager.save_conversation(workspace_id, display_messages)
            return {
                "thread_id": thread_id,
                "checkpoint_id": "",
                "response": response_message,
                "options": None,
                "options_header": None,
                "effect_messages": display_messages,
                "new_effect": None,
                "effect_update": None,
            }
        if "action_payload" in pending_option:
            forced_action = pending_option["action_payload"]
            required_control_ids = pending_option.get("required_control_ids", [])
        else:
            # Compatibility with options stored before control inheritance existed.
            forced_action = pending_option
            required_control_ids = resolve_required_control_ids(
                forced_action.get("user_description", ""),
                serialized_editor_context,
            )
        active_by_id = {
            effect.get("id"): effect
            for effect in effect_list
            if effect.get("status") == "active"
            and effect.get("id") != workspace_id
        }
        authorized_ids = {
            mention.get("effect_id") for mention in effect_mentions
        }
        for reference in forced_action.get("references", []):
            reference_id = reference.get("effect_id", "")
            effect = active_by_id.get(reference_id)
            if effect is not None and reference_id not in authorized_ids:
                effect_mentions.append({
                    "effect_id": reference_id,
                    "display_name": effect.get("name", ""),
                })
                authorized_ids.add(reference_id)
    if _thread_exists(graph, checkpoint_thread_id):
        messages = [
            SystemMessage(content=MAIN_AGENT_SYSTEM, id=_MAIN_SYSTEM_MESSAGE_ID),
            context_message,
            HumanMessage(content=user_input),
        ]
    else:
        stored_history = _chat_manager.get_conversation(workspace_id)
        history = _convert_visible_history_to_messages(stored_history or effect_messages)
        messages = [
            SystemMessage(content=MAIN_AGENT_SYSTEM, id=_MAIN_SYSTEM_MESSAGE_ID),
            context_message,
            *history,
            HumanMessage(content=user_input),
        ]

    initial_state: AgentState = {
        "messages": messages,
        "video_id": video_id,
        "user_input": user_input,
        "effect_id": effect_id,
        "operation": operation,
        "effect_mentions": effect_mentions,
        "pinned_joints": pinned_joints,
        "editor_context": serialized_editor_context,
        "required_control_ids": required_control_ids,
        "main_action": {},
        "action_name": "",
        "action_result": {},
        "action_error": "",
        "inspection_count": 0,
        "pending_options": {},
        "forced_action": forced_action,
        "explicit_parameter_updates": {},
        "effect_messages": effect_messages,
        "prev_code": prev_code,
        "effect_name": effect_name,
        "effect_list": effect_list,
        "injected_reference_ids": [],
        "code": "",
        "params": "",
        "code_status": "",
        "failure_reason": "",
        "last_validated_code": "",
    }

    # Run the StateGraph.
    _thread_local.progress_callback = progress_callback
    agent_events.set_callback(event_callback)
    agent_events.set_cancel_event(cancel_event)
    try:
        if progress_callback:
            progress_callback("thinking", "Understanding your request...")
        graph_config = {"configurable": {"thread_id": checkpoint_thread_id}}
        if resume_checkpoint_id:
            graph_config["configurable"]["checkpoint_id"] = resume_checkpoint_id
        final_state = graph.invoke(initial_state, config=graph_config)
    finally:
        try:
            del _thread_local.progress_callback
        except AttributeError:
            pass
        agent_events.clear_callback()
        agent_events.clear_cancel_event()

    # Record the latest checkpoint for cancellation rollback.
    try:
        snap = graph.get_state({"configurable": {"thread_id": checkpoint_thread_id}})
        checkpoint_id = snap.config.get("configurable", {}).get("checkpoint_id", "")
    except Exception:
        checkpoint_id = ""

    # Execute result handling and build product replies only from verified backend state.
    new_effect = None
    effect_update = final_state.get("action_result", {}).get("effect_update")
    options = None
    options_header = None
    response_message = ""
    response_is_error = False
    action_name = final_state.get("action_name", "respond")
    action = final_state.get("main_action", {})
    action_result = final_state.get("action_result", {})
    code_status = final_state.get("code_status", "")
    code = final_state.get("code", "")
    last_validated_code = final_state.get("last_validated_code", "")
    failure_reason = final_state.get("failure_reason", "")
    action_error = final_state.get("action_error", "")
    final_effect_id = workspace_id
    final_effect_name = final_state.get("effect_name", "Untitled Effect")

    if code_status == "submitted" and code:
        if progress_callback:
            progress_callback("saving", "Saving effect...")
        params_str = final_state.get("params", "{}")
        try:
            new_params = json.loads(params_str) if isinstance(params_str, str) else params_str
        except json.JSONDecodeError:
            new_params = {}

        try:
            saved_effect = _chat_manager.save_generated_effect(
                effect_id=final_effect_id,
                code=code,
                effect_name=final_effect_name,
                base_name=generation_base_name,
                explicit_parameter_updates=final_state.get("explicit_parameter_updates", {}),
                status="active",
                generation_metadata={
                    "operation": operation,
                    "checkpoint_id": checkpoint_id,
                    "references": action.get("references", []),
                },
                editor_context=editor_context,
            )
        except EffectEditorStateError:
            response_message = (
                "The Effect was not saved because a referenced editor control was "
                "deleted or changed during generation. Restore the control or generate "
                "the Effect again."
            )
            response_is_error = True
        else:
            new_params = saved_effect["params"]
            final_effect_name = saved_effect["name"]

            control_count = len(extract_config_labels_and_descriptions(code))
            control_label = "control" if control_count == 1 else "controls"
            response_message = (
                f"{final_effect_name} is ready.\n"
                f"{control_count} {control_label} available in Parameters."
            )

            new_effect = {
                "effect_id": final_effect_id,
                "code": code,
                "params": new_params,
                "parameter_ranges": saved_effect["parameter_ranges"],
                "effect_name": final_effect_name,
                "status": "active",
                "bound_control_ids": saved_effect["bound_control_ids"],
            }
    elif code_status == "failed" and last_validated_code:
        if operation == "edit":
            response_message = (
                "The current Effect was not changed because the generated edit did not "
                "pass validation. Its existing active version is still available."
            )
            response_is_error = True
        else:
            if progress_callback:
                progress_callback("saving", "Saving draft...")
            try:
                saved_effect = _chat_manager.save_draft_effect(
                    effect_id=final_effect_id,
                    code=last_validated_code,
                    effect_name=final_effect_name,
                    base_name=generation_base_name,
                    generation_metadata={
                        "operation": operation,
                        "checkpoint_id": checkpoint_id,
                        "failure_reason": failure_reason,
                        "references": action.get("references", []),
                    },
                    editor_context=editor_context,
                )
            except EffectEditorStateError:
                response_message = (
                    "I could not create a usable effect after validation. "
                    "Please simplify or rephrase the visual behavior and retry."
                )
                response_is_error = True
            else:
                final_effect_name = saved_effect["name"]
                draft_params = saved_effect["params"]
                response_message = (
                    f"{final_effect_name} could not pass validation. "
                    "I saved the best version as a draft so you can preview it or retry."
                )
                response_is_error = True
                new_effect = {
                    "effect_id": final_effect_id,
                    "code": last_validated_code,
                    "params": draft_params,
                    "parameter_ranges": saved_effect["parameter_ranges"],
                    "effect_name": final_effect_name,
                    "status": "draft",
                    "bound_control_ids": saved_effect["bound_control_ids"],
                }

    elif code_status == "failed":
        response_message = (
            "I could not create a usable effect after validation. "
            "Please simplify or rephrase the visual behavior and retry."
        )
        response_is_error = True
    elif action_error == "reference_not_authorized":
        response_message = (
            "I can only use explicitly mentioned active Effects as references. "
            "Mention or select the reference and try again."
        )
        response_is_error = True
    elif action_error == "reference_analysis_failed":
        response_message = (
            "I could not safely analyze the referenced Effect. "
            "Please reduce the references or describe the desired behavior directly."
        )
        response_is_error = True
    elif action_name == "update_effect" and effect_update:
        response_message = f"Updated {effect_update['name']}."
    elif action_name == "update_effect":
        response_message = (
            "I could not apply that direct update. "
            "Please choose the current Effect and use one of its available controls."
        )
        response_is_error = True
    elif action_name == "clarify":
        response_message = action_result.get("question", action.get("question", "Please choose an option."))
        options = action_result.get("options") or None
        options_header = response_message
    elif action_name == "respond":
        response_message = action.get("message", "")
    else:
        response_message = (
            "I could not safely complete that request. Please rephrase it and try again."
        )
        response_is_error = True

    display_messages = _convert_messages_to_dict(final_state["messages"])
    if response_message and (
        not display_messages
        or display_messages[-1].get("role") != "assistant"
        or display_messages[-1].get("content") != response_message
    ):
        response_entry = {"role": "assistant", "content": response_message}
        if response_is_error:
            response_entry["isError"] = True
        display_messages.append(response_entry)
    if effect_id:
        _chat_manager.save_conversation(effect_id, display_messages)

    return {
        "thread_id": thread_id,
        "checkpoint_id": checkpoint_id,
        "response": response_message,
        "options": options,
        "options_header": options_header,
        "effect_messages": display_messages,
        "new_effect": new_effect,
        "effect_update": effect_update,
    }


# ====== Message conversion ======

def _convert_messages_to_dict(messages: list) -> list[dict]:
    """Persist only product-visible user and assistant text."""
    result = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        elif isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": _strip_context_prefix(msg.content)})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls or not isinstance(msg.content, str) or not msg.content.strip():
                continue
            result.append({"role": "assistant", "content": _strip_options_markup(msg.content)})
    return result


def _strip_context_prefix(content: str) -> str:
    """Remove the system-owned context prefix and retain the original user text."""
    return re.sub(r"^(?:\[[^\]]*\]\n)+\n?", "", content)


def _strip_options_markup(content: str) -> str:
    """Remove <options> markup before persisting an assistant response."""
    cleaned = re.sub(r"<options>[\s\S]*?</options>", "", content)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _convert_dict_to_messages(messages: list[dict]) -> list:
    """Restore LangChain messages from persisted conversation dictionaries."""
    result = []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            result.append(HumanMessage(content=msg["content"]))
        elif role == "assistant":
            kwargs = {"content": msg["content"]}
            if "tool_calls" in msg:
                kwargs["tool_calls"] = msg["tool_calls"]
            result.append(AIMessage(**kwargs))
        elif role == "tool":
            result.append(ToolMessage(content=msg["content"], tool_call_id=msg.get("tool_call_id", "")))
    return result


def _convert_visible_history_to_messages(messages: list[dict]) -> list:
    """Restore only product-visible history when bootstrapping a V2 checkpoint."""
    result = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            result.append(HumanMessage(content=_strip_context_prefix(content)))
        elif role == "assistant":
            result.append(AIMessage(content=_strip_options_markup(content)))
    return result
