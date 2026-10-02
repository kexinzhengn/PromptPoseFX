"""MainAgent V3 requirement compiler state-machine tests with Mock LLMs."""

import json

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agent.schemas import CodeAgentResult
from agent.schemas import ReferenceEvidence, ReferenceSafeSummary
from agent.effect_analyzer import ReferenceAnalysisError
from editor_controls import EditorContextSnapshot, EditorSelection, EditorState
from tests.test_agent import _FAKE_CODE
from tests.test_effect_repository import POINT_EFFECT_CODE


def _action_message(name: str, args: dict, call_id: str = "action-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{
        "name": name,
        "args": args,
        "id": call_id,
    }])


def test_generate_action_executes_once_and_backend_reports_saved_result():
    from agent.agent import process_user_message

    model_action = _action_message("generate_effect", {
        "user_description": "Create a violet glow around the left wrist that pulses gently.",
        "requested_name": "Violet Wrist Glow",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = model_action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        result = process_user_message(
            video_id="video-1",
            user_input="给左手腕加一个轻轻脉冲的紫色光晕",
            thread_id="workspace-1",
            effect_id="workspace-1",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert model.invoke.call_count == 1
    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description="Create a violet glow around the left wrist that pulses gently.",
        prev_code="",
    )
    assert result["new_effect"]["effect_name"] == "Violet Wrist Glow"
    assert result["response"].startswith("Violet Wrist Glow is ready")


def test_create_generation_repairs_a_missing_effect_name_before_code_generation():
    from agent.agent import process_user_message

    unnamed = _action_message("generate_effect", {
        "user_description": "Create a smooth wavy line based on path1.",
    })
    named = _action_message("generate_effect", {
        "user_description": "Create a smooth wavy line based on path1.",
        "requested_name": "Flowing Path Wave",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [unnamed, named]
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        result = process_user_message(
            video_id="video-1",
            user_input="Create a smooth wavy line based on path1.",
            thread_id="workspace-name-repair",
            effect_id="workspace-name-repair",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert model.invoke.call_count == 2
    assert "new Effect requires a non-empty requested_name" in (
        model.invoke.call_args_list[1].args[0][-1].content
    )
    code_agent.assert_called_once()
    assert result["new_effect"]["effect_name"] == "Flowing Path Wave"


def test_selected_point_alias_reaches_code_agent_with_trusted_context():
    from agent.agent import process_user_message

    editor_context = EditorContextSnapshot(
        effect_id="workspace-point",
        video_id="video-1",
        editor_revision=1,
        editor_state=EditorState.model_validate({
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [{
                "id": "point-fixed-1",
                "alias": "p1",
                "source": {"type": "fixed", "x": 0.25, "y": 0.75},
            }],
            "markers": [],
            "next_alias": {"point": 2, "marker": 1},
        }),
        selection=EditorSelection(
            current_frame=42,
            selected_point_id="point-fixed-1",
        ),
    )
    model_action = _action_message("generate_effect", {
        "user_description": "Draw a breathing ring at p1.",
        "requested_name": "Point Ring",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = model_action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        process_user_message(
            video_id="video-1",
            user_input="在这里画一个会呼吸的圆环",
            thread_id="workspace-point",
            effect_id="workspace-point",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    model_messages = model.invoke.call_args.args[0]
    trusted_message = next(
        message for message in model_messages
        if message.id == "main-agent-trusted-context-v2"
    )
    assert "point-fixed-1" in trusted_message.content
    assert '"alias": "p1"' in trusted_message.content
    assert '"current_frame": 42' in trusted_message.content
    assert '"x": 0.25' not in trusted_message.content
    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description="Draw a breathing ring at p1.",
        prev_code="",
        editor_context=editor_context.model_dump(mode="json"),
        required_control_ids=["point-fixed-1"],
    )


def test_trusted_context_exposes_selected_path_without_coordinates():
    from agent.agent import _build_trusted_context

    editor_context = {
        "editor_state": {
            "active_interval": {"start_frame": 0, "end_frame": 100},
            "points": [],
            "paths": [{
                "id": "path-stable-1",
                "alias": "path1",
                "points": [{"x": 0.123, "y": 0.234}, {"x": 0.8, "y": 0.7}],
            }],
            "markers": [],
        },
        "selection": {
            "current_frame": 12,
            "selected_point_id": None,
            "selected_path_id": "path-stable-1",
        },
    }

    context = _build_trusted_context(
        "create",
        None,
        [],
        {},
        [],
        editor_context,
    )

    assert '[Editor paths: [{"alias": "path1", "id": "path-stable-1", "point_count": 2}]]' in context
    assert '"selected_path": {"alias": "path1", "id": "path-stable-1", "point_count": 2}' in context
    assert "0.123" not in context


def test_selected_path_alias_reaches_code_agent_as_a_required_control():
    from agent.agent import process_user_message

    editor_context = EditorContextSnapshot(
        effect_id="workspace-path",
        video_id="video-1",
        editor_revision=1,
        editor_state=EditorState.model_validate({
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [],
            "paths": [{
                "id": "path-stable-1",
                "alias": "path1",
                "points": [{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.7}],
            }],
            "markers": [],
            "next_alias": {"point": 1, "marker": 1, "path": 2},
        }),
        selection=EditorSelection(
            current_frame=42,
            selected_path_id="path-stable-1",
        ),
    )
    model_action = _action_message("generate_effect", {
        "user_description": "Render path1 as a luminous violet stroke with a soft pulse.",
        "requested_name": "Violet Drawn Path",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = model_action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        process_user_message(
            video_id="video-1",
            user_input="让这条线发出紫色的光",
            thread_id="workspace-path",
            effect_id="workspace-path",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description="Render path1 as a luminous violet stroke with a soft pulse.",
        prev_code="",
        editor_context=editor_context.model_dump(mode="json"),
        required_control_ids=["path-stable-1"],
    )


def test_time_control_aliases_reach_main_context_and_code_agent_brief():
    from agent.agent import process_user_message

    editor_context = EditorContextSnapshot(
        effect_id="workspace-time",
        video_id="video-1",
        editor_revision=2,
        editor_state=EditorState.model_validate({
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 10, "end_frame": 200},
            "points": [],
            "markers": [
                {"id": "marker-1", "alias": "t1", "frame": 80},
                {"id": "marker-2", "alias": "t2", "frame": 140},
            ],
            "next_alias": {"point": 1, "marker": 3},
        }),
        selection=EditorSelection(current_frame=90),
    )
    model_action = _action_message("generate_effect", {
        "user_description": (
            "Grow a ring continuously over the interval from t1 to t2."
        ),
        "requested_name": "Timed Ring",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = model_action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        process_user_message(
            video_id="video-1",
            user_input="让圆环从t1到t2持续变大",
            thread_id="workspace-time",
            effect_id="workspace-time",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    model_messages = model.invoke.call_args.args[0]
    trusted_message = next(
        message for message in model_messages
        if message.id == "main-agent-trusted-context-v2"
    )
    context = trusted_message.content
    assert '[Effect clip: {"end_frame": 200, "start_frame": 10}]' in context
    assert '"alias": "t1"' in context
    assert '"alias": "t2"' in context
    assert '"frame": 80' not in context
    assert '"frame": 140' not in context
    assert "class Effect" not in context
    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description=(
            "Grow a ring continuously over the interval from t1 to t2."
        ),
        prev_code="",
        editor_context=editor_context.model_dump(mode="json"),
        required_control_ids=["marker-1", "marker-2"],
    )


def test_main_agent_repairs_clarification_that_redefines_existing_marker():
    from agent.agent import _agent_node

    bad_clarification = _action_message("ask_clarification", {
        "question": "What should t1 mean?",
        "options": [
            {
                "label": "Leg motion",
                "description": "Start when the legs move.",
                "brief": {
                    "user_description": "Show a ring when leg motion begins.",
                },
            },
            {
                "label": "Hand contact",
                "description": "Start when a hand reaches a knee.",
                "brief": {
                    "user_description": "Show a ring when a hand reaches a knee.",
                },
            },
        ],
    })
    repaired_generation = _action_message("generate_effect", {
        "user_description": "At t1, show a circular ring around both knees.",
        "requested_name": "Leg Circle",
    })
    state = {
        "messages": [HumanMessage(content="在t1开始，让一个圆形出现在她的腿部。")],
        "user_input": "在t1开始，让一个圆形出现在她的腿部。",
        "required_control_ids": ["marker-1"],
        "editor_context": {
            "editor_state": {
                "points": [],
                "markers": [{"id": "marker-1", "alias": "t1", "frame": 95}],
            },
        },
        "forced_action": {},
    }

    with patch("agent.llm.get_main_agent_llm") as get_llm:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [bad_clarification, repaired_generation]
        get_llm.return_value = model

        result = _agent_node(state)

    assert result["action_name"] == "generate"
    assert result["main_action"]["user_description"].startswith("At t1")
    assert model.invoke.call_count == 2
    repair_messages = model.invoke.call_args_list[1].args[0]
    assert "must preserve existing editor control aliases" in repair_messages[-1].content


def test_main_agent_stops_after_repeated_control_alias_loss():
    from agent.agent import _agent_node

    invalid_action = _action_message("generate_effect", {
        "user_description": "Show a ring when leg motion begins.",
        "requested_name": "Leg Circle",
    })
    state = {
        "messages": [HumanMessage(content="在t1开始，让一个圆形出现在她的腿部。")],
        "user_input": "在t1开始，让一个圆形出现在她的腿部。",
        "required_control_ids": ["marker-1"],
        "editor_context": {
            "editor_state": {
                "points": [],
                "markers": [{"id": "marker-1", "alias": "t1", "frame": 95}],
            },
        },
        "forced_action": {},
    }

    with patch("agent.llm.get_main_agent_llm") as get_llm:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [invalid_action, invalid_action]
        get_llm.return_value = model

        result = _agent_node(state)

    assert result["action_name"] == "respond"
    assert result["action_error"] == "invalid_action"
    assert model.invoke.call_count == 2


def test_selected_option_inherits_marker_requirement_from_original_request():
    from agent.agent import process_user_message

    editor_context = EditorContextSnapshot(
        effect_id="workspace-time-option-inheritance",
        video_id="video-1",
        editor_revision=1,
        editor_state=EditorState.model_validate({
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 200},
            "points": [],
            "markers": [{"id": "marker-1", "alias": "t1", "frame": 95}],
            "next_alias": {"point": 1, "marker": 2},
        }),
        selection=EditorSelection(current_frame=95),
    )
    clarification = _action_message("ask_clarification", {
        "question": "How should the ring behave after t1?",
        "options": [
            {
                "label": "Soft pulse",
                "description": "The ring pulses after t1.",
                "brief": {
                    "user_description": "At t1, show a softly pulsing ring around both knees.",
                    "requested_name": "Leg Pulse",
                },
            },
            {
                "label": "Quick fade",
                "description": "The ring fades shortly after t1.",
                "brief": {
                    "user_description": "At t1, show a ring around both knees that quickly fades.",
                    "requested_name": "Leg Flash",
                },
            },
        ],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = clarification
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        first = process_user_message(
            video_id="video-1",
            user_input="在t1开始，让一个圆形出现在她的腿部。",
            thread_id="workspace-time-option-inheritance",
            effect_id="workspace-time-option-inheritance",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )
        process_user_message(
            video_id="video-1",
            user_input=first["options"][0]["label"],
            selected_option_id=first["options"][0]["id"],
            thread_id="workspace-time-option-inheritance",
            effect_id="workspace-time-option-inheritance",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    assert model.invoke.call_count == 1
    code_agent.assert_called_once()
    assert code_agent.call_args.kwargs["required_control_ids"] == ["marker-1"]


def test_point_moved_during_generation_uses_latest_position_when_saved():
    from agent import agent as agent_module

    repository = agent_module._chat_manager.effects
    created = repository.create_workspace("workspace-moving", "video-1", 230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [{
        "id": "point-1",
        "alias": "p1",
        "source": {"type": "fixed", "x": 0.2, "y": 0.3},
    }]
    editor_state["next_alias"]["point"] = 2
    saved = repository.replace_editor_state("workspace-moving", 0, editor_state)
    editor_context = repository.get_editor_context_snapshot(
        "workspace-moving",
        "video-1",
        saved.editor_revision,
        {"current_frame": 42, "selected_point_id": "point-1"},
    )
    action = _action_message("generate_effect", {
        "user_description": "Draw a breathing ring at p1.",
        "requested_name": "Moving Point",
    })

    def finish_after_move(**kwargs):
        moved_state = repository.get("workspace-moving").editor_state.model_dump(mode="json")
        moved_state["points"][0]["source"]["x"] = 0.8
        repository.replace_editor_state("workspace-moving", 1, moved_state)
        return CodeAgentResult(status="submitted", code=POINT_EFFECT_CODE)

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch(
             "agent.tools.code_agent_module.invoke_code_agent",
             side_effect=finish_after_move,
         ):
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model

        result = agent_module.process_user_message(
            video_id="video-1",
            user_input="在p1画一个呼吸圆环",
            thread_id="workspace-moving",
            effect_id="workspace-moving",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    assert result["new_effect"]["status"] == "active"
    assert result["new_effect"]["bound_control_ids"] == ["point-1"]
    stored = repository.get("workspace-moving")
    assert stored.editor_revision == 2
    assert stored.editor_state.points[0].source.x == 0.8


def test_point_deleted_during_generation_returns_error_without_publishing():
    from agent import agent as agent_module

    repository = agent_module._chat_manager.effects
    created = repository.create_workspace("workspace-deleted", "video-1", 230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [{
        "id": "point-1",
        "alias": "p1",
        "source": {"type": "fixed", "x": 0.2, "y": 0.3},
    }]
    editor_state["next_alias"]["point"] = 2
    saved = repository.replace_editor_state("workspace-deleted", 0, editor_state)
    editor_context = repository.get_editor_context_snapshot(
        "workspace-deleted",
        "video-1",
        saved.editor_revision,
        {"current_frame": 42, "selected_point_id": "point-1"},
    )
    action = _action_message("generate_effect", {
        "user_description": "Draw a breathing ring at p1.",
        "requested_name": "Deleted Point",
    })

    def finish_after_delete(**kwargs):
        deleted_state = repository.get("workspace-deleted").editor_state.model_dump(mode="json")
        deleted_state["points"] = []
        repository.replace_editor_state("workspace-deleted", 1, deleted_state)
        return CodeAgentResult(status="submitted", code=POINT_EFFECT_CODE)

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch(
             "agent.tools.code_agent_module.invoke_code_agent",
             side_effect=finish_after_delete,
         ):
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model

        result = agent_module.process_user_message(
            video_id="video-1",
            user_input="在p1画一个呼吸圆环",
            thread_id="workspace-deleted",
            effect_id="workspace-deleted",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    assert result["new_effect"] is None
    assert result["response"] == (
        "The Effect was not saved because a referenced editor control was deleted or "
        "changed during generation. Restore the control or generate the Effect again."
    )
    stored = repository.get("workspace-deleted")
    assert stored.status == "pending"
    assert stored.code == ""


def test_failed_new_point_effect_can_save_a_draft_with_valid_dependencies():
    from agent import agent as agent_module

    repository = agent_module._chat_manager.effects
    created = repository.create_workspace("workspace-point-draft", "video-1", 230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [{
        "id": "point-1",
        "alias": "p1",
        "source": {"type": "fixed", "x": 0.2, "y": 0.3},
    }]
    editor_state["next_alias"]["point"] = 2
    saved = repository.replace_editor_state("workspace-point-draft", 0, editor_state)
    editor_context = repository.get_editor_context_snapshot(
        "workspace-point-draft",
        "video-1",
        saved.editor_revision,
        {"current_frame": 42, "selected_point_id": "point-1"},
    )
    action = _action_message("generate_effect", {
        "user_description": "Draw a breathing ring at p1.",
        "requested_name": "Point Draft",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(
            status="failed",
            reason="Hard validation failed",
            last_validated_code=POINT_EFFECT_CODE,
        )

        result = agent_module.process_user_message(
            video_id="video-1",
            user_input="在p1画一个呼吸圆环",
            thread_id="workspace-point-draft",
            effect_id="workspace-point-draft",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            editor_context=editor_context,
        )

    assert result["new_effect"]["status"] == "draft"
    assert result["new_effect"]["bound_control_ids"] == ["point-1"]
    stored = repository.get("workspace-point-draft")
    assert stored.status == "draft"
    assert stored.editor_state.points[0].id == "point-1"


def test_update_action_patches_params_and_name_without_code_agent():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "workspace-1",
        _FAKE_CODE,
        {"size": 20},
        "Original",
    )
    model_action = _action_message("update_effect", {
        "requested_name": "Larger Glow",
        "parameter_updates": {"size": 40},
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = model_action
        get_llm.return_value = model

        result = process_user_message(
            video_id="video-1",
            user_input="把大小调到40并改名",
            thread_id="workspace-1",
            effect_id="workspace-1",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    code_agent.assert_not_called()
    assert result["effect_update"] == {
        "effect_id": "workspace-1",
        "name": "Larger Glow",
        "params": {"size": 40},
        "parameter_ranges": {},
        "status": "active",
    }
    assert result["new_effect"] is None
    assert agent_module._chat_manager.get_effect_detail("workspace-1")["code"] == _FAKE_CODE


def test_invalid_action_is_repaired_once_without_executing_the_invalid_tool():
    from agent.agent import process_user_message

    invalid = _action_message("invoke_code_agent", {"user_description": "Legacy action"})
    repaired = AIMessage(content="PromptPoseFX can build effects from pose-joint motion.")

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [invalid, repaired]
        get_llm.return_value = model

        result = process_user_message(
            video_id="video-1",
            user_input="What can this app do?",
            thread_id="workspace-repair",
            effect_id="workspace-repair",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert model.invoke.call_count == 2
    code_agent.assert_not_called()
    assert result["response"] == "PromptPoseFX can build effects from pose-joint motion."


def test_second_invalid_action_returns_deterministic_error_without_tools():
    from agent.agent import process_user_message

    invalid = _action_message("invoke_code_agent", {"user_description": "Legacy action"})

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [invalid, invalid]
        get_llm.return_value = model

        result = process_user_message(
            video_id="video-1",
            user_input="Create something.",
            thread_id="workspace-invalid",
            effect_id="workspace-invalid",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    code_agent.assert_not_called()
    assert result["new_effect"] is None
    assert result["response"] == (
        "I could not safely interpret this request. "
        "Please rephrase it with the target body area and intended visual behavior."
    )


def test_existing_workspace_replaces_a_stale_main_system_prompt(monkeypatch):
    from agent import agent as agent_module

    model = MagicMock()
    model.bind_tools.return_value = model
    model.invoke.side_effect = [
        AIMessage(content="First reply."),
        AIMessage(content="Second reply."),
    ]
    monkeypatch.setattr("agent.llm.get_main_agent_llm", lambda: model)
    monkeypatch.setattr(agent_module, "MAIN_AGENT_SYSTEM", "OLD: p1 must be pinned.")

    agent_module.process_user_message(
        video_id="video-1",
        user_input="First turn",
        thread_id="workspace-stale-prompt",
        effect_id="workspace-stale-prompt",
        effect_messages=[],
        prev_code="",
        effect_name="",
        effect_list=[],
    )
    monkeypatch.setattr(
        agent_module,
        "MAIN_AGENT_SYSTEM",
        "NEW: p1 is an editor Point alias.",
    )

    agent_module.process_user_message(
        video_id="video-1",
        user_input="Second turn",
        thread_id="workspace-stale-prompt",
        effect_id="workspace-stale-prompt",
        effect_messages=[],
        prev_code="",
        effect_name="",
        effect_list=[],
    )

    second_turn_messages = model.invoke.call_args_list[-1].args[0]
    system_messages = [
        message.content for message in second_turn_messages
        if message.id == "main-agent-system-v2"
    ]
    assert system_messages == ["NEW: p1 is an editor Point alias."]


def test_option_id_executes_stored_brief_once_without_reinterpreting():
    from agent.agent import process_user_message

    clarification = _action_message("ask_clarification", {
        "question": "Which complete concept should I create?",
        "options": [
            {
                "label": "Orbiting rings",
                "description": "Cyan rings orbit both wrists.",
                "brief": {
                    "user_description": "Create two cyan rings orbiting both wrists.",
                    "requested_name": "Orbiting Wrist Rings",
                },
            },
            {
                "label": "Rising stream",
                "description": "Violet energy rises from both wrists.",
                "brief": {
                    "user_description": "Create violet energy rising from both wrists.",
                    "requested_name": "Rising Wrist Energy",
                },
            },
            {
                "label": "Pulse halo",
                "description": "Amber halos pulse around both wrists.",
                "brief": {
                    "user_description": "Create amber halos pulsing around both wrists.",
                    "requested_name": "Wrist Pulse Halos",
                },
            },
        ],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = clarification
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        first = process_user_message(
            video_id="video-1",
            user_input="Give me ideas.",
            thread_id="workspace-options",
            effect_id="workspace-options",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )
        option_id = first["options"][0]["id"]
        selected = process_user_message(
            video_id="video-1",
            user_input="Orbiting rings",
            selected_option_id=option_id,
            thread_id="workspace-options",
            effect_id="workspace-options",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )
        repeated = process_user_message(
            video_id="video-1",
            user_input="Orbiting rings",
            selected_option_id=option_id,
            thread_id="workspace-options",
            effect_id="workspace-options",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert first["options_header"] == "Which complete concept should I create?"
    assert len(first["options"]) == 3
    assert model.invoke.call_count == 1
    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description="Create two cyan rings orbiting both wrists.",
        prev_code="",
    )
    assert selected["new_effect"]["effect_name"] == "Orbiting Wrist Rings"
    assert repeated["new_effect"] is None
    assert repeated["response"] == "That option is no longer available. Please choose or describe a new idea."


def test_mixed_edit_generates_code_and_applies_explicit_control_value():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "workspace-mixed",
        _FAKE_CODE,
        {"size": 20},
        "Original Glow",
    )
    action = _action_message("generate_effect", {
        "user_description": "Make the current glow spiral while preserving its wrist anchor.",
        "requested_name": "Spiral Glow",
        "parameter_updates": {"size": 40},
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        result = process_user_message(
            video_id="video-1",
            user_input="让光晕变成螺旋，同时把大小调到40",
            thread_id="workspace-mixed",
            effect_id="workspace-mixed",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    code_agent.assert_called_once_with(
        video_id="video-1",
        user_description="Make the current glow spiral while preserving its wrist anchor.",
        prev_code=_FAKE_CODE,
    )
    assert result["new_effect"]["params"]["size"] == 40


def test_pinned_joint_alias_is_expanded_before_code_agent():
    from agent.agent import process_user_message

    model_description = (
        "Create a soft cyan pulse at p1 with a cycle of "
        "2 seconds (60 frames at 30 FPS)."
    )
    compiled_description = (
        "Create a soft cyan pulse at right_wrist with a cycle of "
        "2 seconds (60 frames at 30 FPS)."
    )
    action = _action_message("generate_effect", {
        "user_description": model_description,
        "requested_name": "Cyan Wrist Pulse",
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        process_user_message(
            video_id="video-1",
            user_input="在p1做一个2秒循环的青色脉冲",
            thread_id="workspace-pin",
            effect_id="workspace-pin",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            pinned_joints={"p1": "right_wrist"},
        )

    assert code_agent.call_args.kwargs["user_description"] == compiled_description


def test_unsupported_pixel_request_returns_pose_only_alternative_without_generation():
    from agent.agent import process_user_message

    response = AIMessage(
        content=(
            "PromptPoseFX cannot sample clothing color from video pixels. "
            "It can instead attach a user-chosen color glow to the shoulders and hips."
        )
    )

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = response
        get_llm.return_value = model

        result = process_user_message(
            video_id="video-1",
            user_input="读取衣服颜色做同色光晕",
            thread_id="workspace-pixels",
            effect_id="workspace-pixels",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    code_agent.assert_not_called()
    assert "cannot sample clothing color" in result["response"]
    assert "shoulders and hips" in result["response"]


def test_read_only_inspection_can_be_followed_by_one_product_response():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "reference-active",
        _FAKE_CODE,
        {"size": 28},
        "Reference Glow",
        status="active",
    )
    inspect_action = _action_message("inspect_effects", {
        "effect_ids": ["reference-active"],
        "question": "What controls does this Effect expose?",
    })
    answer = AIMessage(content="Reference Glow exposes a size control.")

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.side_effect = [inspect_action, answer]
        get_llm.return_value = model
        analyzer_class.return_value.summarize_many.return_value = [
            ReferenceSafeSummary(
                effect_id="reference-active",
                summary="A compact glow follows its anchor and expands with its size control.",
            )
        ]

        result = process_user_message(
            video_id="video-1",
            user_input="What can I adjust on Reference Glow?",
            thread_id="workspace-inspect",
            effect_id="workspace-inspect",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert model.invoke.call_count == 2
    source = analyzer_class.return_value.summarize_many.call_args.args[0][0]
    assert source.code == _FAKE_CODE
    second_model_input = model.invoke.call_args_list[1].args[0]
    assert any(
        "A compact glow follows its anchor" in str(message.content)
        for message in second_model_input
    )
    inspection_messages = [
        str(message.content)
        for message in second_model_input
        if message.__class__.__name__ == "ToolMessage"
    ]
    assert inspection_messages
    inspection_result = json.loads(inspection_messages[-1])
    assert set(inspection_result["effects"][0]) == {
        "effect_id", "name", "summary",
    }
    code_agent.assert_not_called()
    assert result["response"] == "Reference Glow exposes a size control."
    assert all(message["role"] != "tool" for message in result["effect_messages"])
    assert all("class Effect" not in message["content"] for message in result["effect_messages"])


def test_explicit_active_reference_is_analyzed_and_injected_without_persisting_evidence():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    reference_code = _FAKE_CODE.replace(
        "display(sketch",
        "/* pulseEvidenceToken */\n  display(sketch",
    )
    agent_module._chat_manager.save_effect(
        "reference-active",
        reference_code,
        {"size": 28},
        "Reference Glow",
        status="active",
    )
    action = _action_message("generate_effect", {
        "user_description": "Create a blue wrist glow using the referenced pulse rhythm.",
        "requested_name": "Referenced Blue Glow",
        "references": [{
            "effect_id": "reference-active",
            "reference_intent": "Reuse only the pulse rhythm.",
        }],
    })
    evidence = ReferenceEvidence.model_validate({
        "effect_id": "reference-active",
        "reference_intent": "Reuse only the pulse rhythm.",
        "findings": [{
            "role": "pulse rhythm",
            "evidence": "pulseEvidenceToken",
            "usage": "Reuse only the rhythmic size modulation.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        analyzer_class.return_value.analyze_evidence.return_value = [evidence]
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        result = process_user_message(
            video_id="video-1",
            user_input="参考 @Reference Glow 的脉冲节奏，做一个蓝色手腕光晕",
            thread_id="workspace-reference",
            effect_id="workspace-reference",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[{
                "effect_id": "reference-active",
                "display_name": "Reference Glow",
            }],
        )

    source = analyzer_class.return_value.analyze_evidence.call_args.args[0][0]
    assert source.effect_id == "reference-active"
    assert source.code == reference_code
    assert code_agent.call_args.kwargs["reference_evidence"][0]["effect_id"] == "reference-active"
    metadata = agent_module._chat_manager.get_effect_detail(
        result["new_effect"]["effect_id"]
    )["generation_metadata"]
    assert metadata["references"] == [{
        "effect_id": "reference-active",
        "reference_intent": "Reuse only the pulse rhythm.",
    }]
    assert "evidence" not in str(metadata)
    snapshot = agent_module._get_main_graph().get_state({
        "configurable": {"thread_id": "main-agent-v2:workspace-reference"}
    })
    assert "pulseEvidenceToken" not in str(snapshot.values)
    assert all(
        "pulseEvidenceToken" not in message["content"]
        for message in result["effect_messages"]
    )


def test_unmentioned_reference_is_rejected_without_analyzer_or_code_agent():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "reference-active",
        _FAKE_CODE,
        {"size": 28},
        "Reference Glow",
        status="active",
    )
    action = _action_message("generate_effect", {
        "user_description": "Create a copied glow.",
        "requested_name": "Copied Glow",
        "references": [{
            "effect_id": "reference-active",
            "reference_intent": "Copy everything.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model

        result = process_user_message(
            video_id="video-1",
            user_input="Create a glow.",
            thread_id="workspace-unmentioned",
            effect_id="workspace-unmentioned",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    analyzer_class.assert_not_called()
    code_agent.assert_not_called()
    assert result["new_effect"] is None
    assert "reference" in result["response"].lower()


def test_reference_analysis_failure_stops_generation():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "reference-active",
        _FAKE_CODE,
        {"size": 28},
        "Reference Glow",
        status="active",
    )
    action = _action_message("generate_effect", {
        "user_description": "Create a related wrist glow.",
        "requested_name": "Related Wrist Glow",
        "references": [{
            "effect_id": "reference-active",
            "reference_intent": "Reuse the motion.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.agent.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        analyzer_class.return_value.analyze_evidence.side_effect = ReferenceAnalysisError(
            "invalid evidence"
        )

        result = process_user_message(
            video_id="video-1",
            user_input="参考 @Reference Glow 的运动",
            thread_id="workspace-analysis-failure",
            effect_id="workspace-analysis-failure",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[{
                "effect_id": "reference-active",
                "display_name": "Reference Glow",
            }],
        )

    code_agent.assert_not_called()
    assert result["new_effect"] is None
    assert result["response"] == (
        "I could not safely analyze the referenced Effect. "
        "Please reduce the references or describe the desired behavior directly."
    )


def test_previous_effect_phrase_resolves_to_latest_other_active_effect():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "older-active", _FAKE_CODE, {"size": 20}, "Older", status="active"
    )
    agent_module._chat_manager.save_effect(
        "latest-active", _FAKE_CODE, {"size": 24}, "Latest", status="active"
    )
    action = _action_message("generate_effect", {
        "user_description": "Create a new glow using the previous Effect's pacing.",
        "requested_name": "Paced Glow",
        "references": [{
            "effect_id": "latest-active",
            "reference_intent": "Reuse only its pacing.",
        }],
    })
    evidence = ReferenceEvidence.model_validate({
        "effect_id": "latest-active",
        "reference_intent": "Reuse only its pacing.",
        "findings": [{
            "role": "pacing",
            "evidence": "params.size",
            "usage": "Reuse the pacing only.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        analyzer_class.return_value.analyze_evidence.return_value = [evidence]
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        process_user_message(
            video_id="video-1",
            user_input="参考上一个效果的节奏做一个新光晕",
            thread_id="workspace-previous",
            effect_id="workspace-previous",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    source = analyzer_class.return_value.analyze_evidence.call_args.args[0][0]
    assert source.effect_id == "latest-active"


def test_explicit_unique_fuzzy_reference_can_use_active_metadata_without_mention():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "blue-ribbon",
        _FAKE_CODE,
        {"size": 24},
        "Blue Ribbon",
        status="active",
    )
    action = _action_message("generate_effect", {
        "user_description": "Create a wrist glow inspired by the blue ribbon Effect.",
        "requested_name": "Blue Ribbon Wrist Glow",
        "references": [{
            "effect_id": "blue-ribbon",
            "reference_intent": "Reuse its flowing motion.",
        }],
    })
    evidence = ReferenceEvidence.model_validate({
        "effect_id": "blue-ribbon",
        "reference_intent": "Reuse its flowing motion.",
        "findings": [{
            "role": "flow",
            "evidence": "params.size",
            "usage": "Reuse its flowing motion.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = action
        get_llm.return_value = model
        analyzer_class.return_value.analyze_evidence.return_value = [evidence]
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        result = process_user_message(
            video_id="video-1",
            user_input="参考那个蓝色丝带效果的流动感做一个手腕光晕",
            thread_id="workspace-fuzzy-reference",
            effect_id="workspace-fuzzy-reference",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["new_effect"] is not None
    source = analyzer_class.return_value.analyze_evidence.call_args.args[0][0]
    assert source.effect_id == "blue-ribbon"


def test_selected_reference_idea_keeps_its_one_use_reference_authorization():
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "reference-active",
        _FAKE_CODE,
        {"size": 24},
        "Reference Glow",
        status="active",
    )
    clarification = _action_message("ask_clarification", {
        "question": "Which related concept should I create?",
        "options": [
            {
                "label": "Orbit glow",
                "description": "A cyan glow orbits the wrist.",
                    "brief": {
                        "user_description": "Create a cyan wrist glow using the reference pacing.",
                        "requested_name": "Orbit Glow",
                        "references": [{
                        "effect_id": "reference-active",
                        "reference_intent": "Reuse only the pacing.",
                    }],
                },
            },
            {
                "label": "Pulse glow",
                "description": "A violet glow pulses at the wrist.",
                    "brief": {
                        "user_description": "Create a violet wrist pulse using the reference pacing.",
                        "requested_name": "Pulse Glow",
                        "references": [{
                        "effect_id": "reference-active",
                        "reference_intent": "Reuse only the pacing.",
                    }],
                },
            },
        ],
    })
    evidence = ReferenceEvidence.model_validate({
        "effect_id": "reference-active",
        "reference_intent": "Reuse only the pacing.",
        "findings": [{
            "role": "pacing",
            "evidence": "params.size",
            "usage": "Reuse the pacing only.",
        }],
    })

    with patch("agent.llm.get_main_agent_llm") as get_llm, \
         patch("agent.agent.EffectAnalyzer") as analyzer_class, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as code_agent:
        model = MagicMock()
        model.bind_tools.return_value = model
        model.invoke.return_value = clarification
        get_llm.return_value = model
        analyzer_class.return_value.analyze_evidence.return_value = [evidence]
        code_agent.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        first = process_user_message(
            video_id="video-1",
            user_input="参考 @Reference Glow 给我一些创意",
            thread_id="workspace-reference-option",
            effect_id="workspace-reference-option",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[{
                "effect_id": "reference-active",
                "display_name": "Reference Glow",
            }],
        )
        selected = process_user_message(
            video_id="video-1",
            user_input=first["options"][0]["label"],
            selected_option_id=first["options"][0]["id"],
            thread_id="workspace-reference-option",
            effect_id="workspace-reference-option",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[],
        )

    assert selected["new_effect"] is not None
    assert analyzer_class.return_value.analyze_evidence.call_count == 1
