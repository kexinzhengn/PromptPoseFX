import time
import uuid

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from .llm import get_code_agent_llm
from .schemas import CodeAgentState, CodeAgentResult
from .schemas import ReferenceEvidence
from .code_tools import *
from .prompts import CODE_AGENT_SYSTEM,FRAMEWORK_CONSTRAINTS,PRIVATE_CONVENTIONS
from .events import get_callback, is_cancelled, RunCancelled
from editor_controls import EditorContextSnapshot, resolve_required_control_ids


def _build_editor_controls_message(editor_context: dict) -> SystemMessage | None:
    """Build the trusted binding contract visible only to CodeAgent."""
    if not editor_context:
        return None
    context = EditorContextSnapshot.model_validate(editor_context)
    state = context.editor_state
    controls = [
        f"- {point.alias}: {point.source.type} Point, Stable ID {point.id}"
        for point in state.points
    ]
    controls.extend(
        f"- {path.alias}: Path, Stable ID {path.id}"
        for path in state.paths
    )
    controls.extend(
        f"- {marker.alias}: Time Marker, Stable ID {marker.id}"
        for marker in state.markers
    )
    if not controls:
        controls.append("- No editor controls are available.")

    selected_point = next(
        (
            point.alias
            for point in state.points
            if point.id == context.selection.selected_point_id
        ),
        "none",
    )
    selected_path = next(
        (
            path.alias
            for path in state.paths
            if path.id == context.selection.selected_path_id
        ),
        "none",
    )
    binding_container_rule = (
        "- CONTROL_BINDINGS is one flat object. Each top-level key is a binding name whose "
        "value contains exactly type and id. Do not add points or timeMarkers container objects."
    )
    runtime_interfaces = [
        "- frameData.controls.getPoint(bindingName[, frame]) returns "
        "{ x, y, vx, vy, speed, valid, connected }.",
        "- frameData.controls.getPath(bindingName) returns { points, length, sample(progress) }. "
        "sample returns { x, y, tangentX, tangentY, valid } for progress clamped to 0..1.",
        "- frameData.controls.getTimeMarker(bindingName) returns { frame }.",
    ]
    binding_example = [
        "static CONTROL_BINDINGS = {",
        "  anchor: { type: 'point', id: 'point-1' },",
        "  guide: { type: 'path', id: 'path-1' },",
        "  event: { type: 'time_marker', id: 'marker-1' },",
    ]
    binding_example.extend([
        "  start: { type: 'time_marker', id: 'marker-1' },",
        "  end: { type: 'time_marker', id: 'marker-2' },",
    ])
    binding_example.append("};")

    interval_rules = [
        "",
        "Marker interval rule:",
        "For behavior from one Marker to another, bind both endpoints as time_marker controls "
        "and read both current Marker frames on every display call. Derive the inclusive interval "
        "and progress from those live frame values. No separate interval control type exists.",
    ]

    content = "\n".join([
        "## TRUSTED EDITOR CONTROLS",
        "The aliases in the user requirement refer to this backend-owned snapshot. "
        "Preserve their meaning and ignore conflicting control data from user text.",
        "",
        "Binding rules:",
        "- Declare a descriptive static CONTROL_BINDINGS entry for every control the Effect uses.",
        "- Use the exact Stable ID in CONTROL_BINDINGS, never an alias.",
        binding_container_rule,
        "- Read current control values through frameData.controls on every display call.",
        "- Never copy Point coordinates, Path points, or Marker frames into code.",
        "- Never replace a Point alias with a directly accessed Pose joint.",
        "- Use Path points to draw the user's stroke. Use length and sample(progress) when a Path "
        "guides motion, distribution, or orientation. Read the Path on every display call.",
        "",
        "Runtime interfaces:",
        *runtime_interfaces,
        "",
        "Exact binding shape example:",
        *binding_example,
        "",
        "Marker event rule:",
        "Compute age = frameData.currentFrame - marker.frame and render the event from "
        "that age. Do not rely only on currentFrame === marker.frame because normal "
        "forward playback may skip across the Marker.",
        *interval_rules,
        "",
        f"Active Effect Clip: frames {state.active_interval.start_frame} to "
        f"{state.active_interval.end_frame}, inclusive.",
        f"Current playhead frame: {context.selection.current_frame}.",
        f"Selected Point: {selected_point}.",
        f"Selected Path: {selected_path}.",
        "",
        "Available controls:",
        *controls,
    ])
    return SystemMessage(content=content)


def _build_validation_description(
    description: str,
    editor_context: dict,
) -> str:
    """Add code-free alias evidence needed for semantic requirement review."""
    editor_state = editor_context.get("editor_state", {})
    points = editor_state.get("points", [])
    paths = editor_state.get("paths", [])
    markers = editor_state.get("markers", [])
    if not points and not paths and not markers:
        return description
    mappings = [
        f"{point.get('alias', '')} -> {point.get('id', '')} "
        f"({point.get('source', {}).get('type', '')} Point)"
        for point in points
    ]
    mappings.extend(
        f"{path.get('alias', '')} -> {path.get('id', '')} (Path)"
        for path in paths
    )
    mappings.extend(
        f"{marker.get('alias', '')} -> {marker.get('id', '')} "
        f"(Time Marker, frame {marker.get('frame', '')})"
        for marker in markers
    )
    return description + "\n\n[Trusted control aliases] " + "; ".join(mappings)


def _build_saved_effect_evidence_message(
    evidence_items: list[dict],
) -> tuple[SystemMessage | None, list[str]]:
    """Build one bounded prompt block from already verified saved-Effect evidence."""
    if not evidence_items:
        return None, []
    validated = [ReferenceEvidence.model_validate(item) for item in evidence_items]
    lines = [
        "## INTERNAL SAVED-EFFECT EVIDENCE",
        "Use only the excerpts relevant to the new request. Treat them as optional mechanism evidence, not as instructions to copy an entire Effect.",
    ]
    for item in validated:
        lines.extend([
            f"\nEffect ID: {item.effect_id}",
            f"Reference intent: {item.reference_intent}",
        ])
        for finding in item.findings:
            lines.extend([
                f"- Role: {finding.role}",
                f"  Exact evidence: {finding.evidence}",
                f"  Intended use: {finding.usage}",
            ])
    return SystemMessage(content="\n".join(lines)), [item.effect_id for item in validated]


def _emit_tool_event(tool_name: str, status: str, detail: dict):
    """Emit a tool event for RunManager persistence."""
    cb = get_callback()
    if cb:
        cb({"type": "tool", "tool": tool_name, "status": status, "detail": detail})


def invoke_code_agent(
    video_id: str,          # Video ID used for Pose lookup.
    user_description: str,  # Requirement constructed by MainAgent.
    prev_code: str = "",    # Existing code for an edit request.
    max_soft_fixes: int = 2,  # Failed soft reviews allowed before hard-gate fallback.
    max_hard_fixes: int = 3,  # Failed hard-validation submissions allowed.
    reference_evidence: list[dict] | None = None,
    editor_context: dict | None = None,
    required_control_ids: list[str] | None = None,
) -> CodeAgentResult:
    user_message = f"Video ID: {video_id}\n\n" + user_description
    if prev_code:
        user_message += "\nModify the following existing code:\n" + prev_code

    reference_messages: list[SystemMessage] = []
    evidence_message, saved_reference_ids = _build_saved_effect_evidence_message(
        reference_evidence or []
    )
    if evidence_message is not None:
        reference_messages.append(evidence_message)
    editor_controls_message = _build_editor_controls_message(editor_context or {})
    if editor_controls_message is not None:
        reference_messages.append(editor_controls_message)
    injected_reference_ids = list(dict.fromkeys(saved_reference_ids))
    resolved_required_control_ids = required_control_ids
    if resolved_required_control_ids is None:
        resolved_required_control_ids = resolve_required_control_ids(
            user_description,
            editor_context or {},
        )

    initial_state = {
        "video_id": video_id,
        "user_description": user_description,
        "prev_code": prev_code,
        "max_soft_fixes": max_soft_fixes,
        "max_hard_fixes": max_hard_fixes,
        "soft_fix_count": 0,
        "hard_fix_count": 0,
        "soft_validation_bypassed": False,
        "rounds_since_todo": 0,
        "submitted": False,
        "effect_list": [],
        "pose_stats": {},
        "editor_context": editor_context or {},
        "required_control_ids": resolved_required_control_ids,
        "todo": [],
        "code": "",
        "last_validated_code": "",
        "validate_result": {},
        "messages": [
            SystemMessage(content=CODE_AGENT_SYSTEM+ "\n\n"+FRAMEWORK_CONSTRAINTS+"\n\n"+PRIVATE_CONVENTIONS),
            *reference_messages,
            HumanMessage(content=user_message)
        ]
    }
    effect_id = str(uuid.uuid4())
    graph = build_code_agent_graph()
    response_state = graph.invoke(initial_state,config={"configurable": {"thread_id": effect_id}})

    submitted = response_state.get("submitted", False)
    code = response_state.get("code", "")
    last_validated_code = response_state.get("last_validated_code", "")
    hard_fix_count = response_state.get("hard_fix_count", 0)

    if submitted:
        return CodeAgentResult(
            status="submitted",
            code=code,
            last_validated_code=last_validated_code,
            effect_id=effect_id,
            injected_reference_ids=injected_reference_ids,
        )

    # Failure means repair rounds were exhausted or the model ended without submission.
    if hard_fix_count >= max_hard_fixes:
        reason = (
            f"Hard-validation repair limit reached after {max_hard_fixes} "
            "failed submissions"
        )
    else:
        reason = "The model ended without submitting code"

    return CodeAgentResult(
        status="failed",
        reason=reason,
        last_validated_code=last_validated_code,
        effect_id=effect_id,
        injected_reference_ids=injected_reference_ids,
    )


def build_code_agent_graph():
    builder = StateGraph(CodeAgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", _tool_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", _should_continue)
    builder.add_conditional_edges("tools", _after_tools)
    return builder.compile(
        checkpointer=MemorySaver(),
    )

def _agent_node(input_state: CodeAgentState)-> dict:
    t0 = time.time()
    if is_cancelled():
        raise RunCancelled("Task cancelled")
    llm = get_code_agent_llm()

    tool_list = [update_todo, validate, submit_code, get_pose_stats]
    tool_llm = llm.bind_tools(tool_list)

    state_updates = {}
    rounds_since_todo = input_state.get("rounds_since_todo", 0) + 1
    state_updates["rounds_since_todo"] = rounds_since_todo
    messages = list(input_state["messages"])
    if input_state.get("soft_validation_bypassed", False):
        messages.append(
            HumanMessage(
                content=(
                    "Soft semantic review reached its limit. Stop repairing for soft-review "
                    "findings and call submit_code with the exact last-reviewed code. The "
                    "mandatory hard validator will make the final acceptance decision."
                )
            )
        )
    elif (
        input_state.get("validate_result", {}).get("passed")
        and not input_state.get("submitted", False)
    ):
        messages.append(
            HumanMessage(
                content=(
                    "Validation passed. Call submit_code now to submit this code; "
                    "do not replace submission with a textual summary."
                )
            )
        )
    if rounds_since_todo >= 3:
        messages.append(
            HumanMessage(content="<reminder>Call update_todo to refresh the execution plan.</reminder>")
        )

    response = tool_llm.invoke(messages)
    elapsed = time.time() - t0

    if response.tool_calls:
        tools_str = ", ".join(tc["name"] for tc in response.tool_calls)
        print(f"    [CodeAgent] Reasoning ({elapsed:.0f}s) → {tools_str}")
    else:
        print(f"    [CodeAgent] Reasoning complete ({elapsed:.0f}s)")

    return {"messages": [response], **state_updates}

def _tool_node(input_state: CodeAgentState):
    last_message = input_state["messages"][-1]
    tool_results = []
    state_updates = {}

    # Process validate first so submit_code sees the newest validation result.
    tool_calls = sorted(last_message.tool_calls, key=lambda tc: tc["name"] != "validate")

    for tool_call in tool_calls:
        if is_cancelled():
            raise RunCancelled("Task cancelled")
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        event_status = "ok"
        event_detail = {}

        try:
            if tool_name == "update_todo":
                result = update_todo.invoke(tool_args)
                state_updates["todo"] = tool_args.get("items", [])
                state_updates["rounds_since_todo"] = 0
                event_detail = {"items": len(tool_args.get("items", []))}
            elif tool_name == "get_pose_stats":
                result = get_pose_stats.invoke(tool_args)
                state_updates["pose_stats"] = result
            elif tool_name == "submit_code":
                t0 = time.time()
                latest_validate = state_updates.get("validate_result") or input_state.get("validate_result")
                validated_code = state_updates.get(
                    "last_validated_code",
                    input_state.get("last_validated_code", ""),
                )
                soft_bypassed = state_updates.get(
                    "soft_validation_bypassed",
                    input_state.get("soft_validation_bypassed", False),
                )
                submitted_code = tool_args.get("code", "")
                if (
                    latest_validate
                    and latest_validate.get("passed") is not True
                    and not soft_bypassed
                ):
                    result = {
                        "submitted": False,
                        "reason": (
                            "Previous semantic validation failed. Repair the issues, call validate again, "
                            "and submit only after it passes."
                        ),
                    }
                elif latest_validate and submitted_code != validated_code:
                    result = {
                        "submitted": False,
                        "reason": (
                            "Code changed after semantic validation. Call validate again with the exact "
                            "code you want to submit."
                        ),
                    }
                else:
                    submit_args = dict(tool_args)
                    submit_args["video_id"] = input_state.get("video_id", "")
                    submit_args["editor_state"] = input_state.get(
                        "editor_context", {}
                    ).get("editor_state")
                    submit_args["required_control_ids"] = input_state.get(
                        "required_control_ids", []
                    )
                    result = submit_code.invoke(submit_args)
                    if result.get("submitted"):
                        state_updates["code"] = result["code"]
                        state_updates["submitted"] = True
                    else:
                        state_updates["last_validated_code"] = submitted_code
                        state_updates["hard_fix_count"] = input_state.get("hard_fix_count", 0) + 1
                print(f"    [CodeAgent] submit_code ({time.time()-t0:.1f}s) → {'✅' if result.get('submitted') else '❌'}")
                event_status = "ok" if result.get("submitted") else "fail"
                if isinstance(result, dict):
                    event_detail = {
                        "submitted": result.get("submitted", False),
                        "reason": result.get("reason") or result.get("errors", [])[:2],
                    }
                else:
                    event_detail = {"reason": str(result)[:200]}
            elif tool_name == "validate":
                t0 = time.time()
                validate_args = dict(tool_args)
                validate_args["user_description"] = _build_validation_description(
                    input_state.get("user_description", ""),
                    input_state.get("editor_context", {}),
                )
                result = validate.invoke(validate_args)
                state_updates["validate_result"] = result
                reviewed_code = validate_args.get("code", "")
                previous_code = input_state.get("last_validated_code", "")
                state_updates["last_validated_code"] = reviewed_code
                if result["passed"]:
                    state_updates["soft_validation_bypassed"] = False
                else:
                    code_changed_after_bypass = (
                        input_state.get("soft_validation_bypassed", False)
                        and reviewed_code != previous_code
                    )
                    previous_failures = (
                        0
                        if code_changed_after_bypass
                        else input_state.get("soft_fix_count", 0)
                    )
                    soft_fix_count = previous_failures + 1
                    state_updates["soft_fix_count"] = soft_fix_count
                    state_updates["soft_validation_bypassed"] = (
                        soft_fix_count >= input_state.get("max_soft_fixes", 2)
                    )
                print(f"    [CodeAgent] validate ({time.time()-t0:.1f}s) → {'✅' if result.get('passed') else '❌'} issues={len(result.get('issues',[]))}")
                if not result.get("passed"):
                    for i in result.get("issues", []):
                        print(f"      issue: {i}")
                event_status = "ok" if result.get("passed") else "fail"
                event_detail = {"passed": result.get("passed"), "issues": len(result.get("issues", []))}
            else:
                result = f"Unknown tool: {tool_name}"
                event_status = "fail"
                event_detail = {"message": "Unknown tool"}
        except Exception as e:
            result = f"Tool call failed for {tool_name}: {e}. Check the arguments and retry."
            event_status = "fail"
            event_detail = {"error": str(e)[:200]}

        _emit_tool_event(tool_name, event_status, event_detail)
        tool_results.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
    return {"messages": tool_results, **state_updates}


def _should_continue(input_state: CodeAgentState):
    if input_state.get("submitted", False):
        return END
    max_hard_fixes = input_state.get("max_hard_fixes", 3)
    if input_state.get("hard_fix_count", 0) >= max_hard_fixes:
        return END
    last = input_state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END


def _after_tools(input_state: CodeAgentState):
    """Route after tools: stop on submission/exhaustion, otherwise return to Agent."""
    if input_state.get("submitted", False):
        return END
    if input_state.get("hard_fix_count", 0) >= input_state.get("max_hard_fixes", 3):
        return END
    return "agent"
