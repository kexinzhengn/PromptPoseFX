"""主 Agent 状态图测试（Mock LLM，避免真实调用）"""

from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END


# ====== 编译 ======

def test_build_main_agent_graph():
    from agent.agent import build_main_agent_graph
    graph = build_main_agent_graph()
    assert "Compiled" in type(graph).__name__


def test_main_prompt_keeps_current_edit_context_system_owned():
    """MainAgent must not retrieve or reproduce the current effect code."""
    from agent.prompts import MAIN_AGENT_SYSTEM

    assert "never receives Effect source code" in MAIN_AGENT_SYSTEM
    assert "Do not ask for, reproduce, or expose code" in MAIN_AGENT_SYSTEM


# ====== should_continue ======

def test_should_continue_tools():
    from agent.agent import _should_continue
    from agent.schemas import AgentState
    state = AgentState(
        messages=[AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "c1"}])],
        video_id="", user_input="", effect_id="",
        effect_messages=[], prev_code="", effect_name="",
        effect_list=[], code="", params="", action_name="generate",
    )
    assert _should_continue(state) == "tools"


def test_should_continue_end():
    from agent.agent import _should_continue
    from agent.schemas import AgentState
    state = AgentState(
        messages=[AIMessage(content="任务完成")],
        video_id="", user_input="", effect_id="",
        effect_messages=[], prev_code="", effect_name="",
        effect_list=[], code="", params="",
    )
    assert _should_continue(state) == END


# ====== 消息转换 ======

def test_message_conversion_keeps_only_product_conversation():
    from agent.agent import _convert_messages_to_dict, _convert_dict_to_messages
    original = [
        HumanMessage(content="你好"),
        AIMessage(content="你好！"),
        ToolMessage(content='{"ok": true}', tool_call_id="t1"),
    ]
    as_dict = _convert_messages_to_dict(original)
    assert len(as_dict) == 2
    assert as_dict[0]["role"] == "user"
    assert as_dict[1]["role"] == "assistant"

    restored = _convert_dict_to_messages(as_dict)
    assert len(restored) == 2
    assert isinstance(restored[0], HumanMessage)
    assert isinstance(restored[1], AIMessage)


def test_message_conversion_skips_system():
    from langchain_core.messages import SystemMessage
    from agent.agent import _convert_messages_to_dict
    msgs = [SystemMessage(content="你是一个助手"), HumanMessage(content="hi")]
    result = _convert_messages_to_dict(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "user"


def test_strip_context_prefix():
    """用户消息存档时去掉上下文前缀，只留用户原话"""
    from agent.agent import _strip_context_prefix

    content = "[Current effect name: 能量光环]\n[No saved effects]\n\n你好，帮我改一下"
    assert _strip_context_prefix(content) == "你好，帮我改一下"
    assert _strip_context_prefix("普通消息") == "普通消息"
    # 用户输入本身以 [ 开头也不误删（前缀后有空行分隔）
    assert _strip_context_prefix("[No saved effects]\n\n[你好]") == "[你好]"


def test_strip_options_markup():
    """助手消息存档时去掉 <options> 标记，只留问题文字"""
    from agent.agent import _strip_options_markup

    content = (
        "请选择你想要的风格\n"
        "<options>\n<header>风格</header>\n"
        '<option label="火焰" description="拖尾"/>\n'
        '<option label="闪电" description="雷电"/>\n'
        "</options>\n也可以直接输入你的想法"
    )
    result = _strip_options_markup(content)
    assert "<options>" not in result
    assert "火焰" not in result
    assert "请选择你想要的风格" in result
    assert "也可以直接输入你的想法" in result
    assert _strip_options_markup("普通回复") == "普通回复"


def test_message_conversion_drops_tool_calls_and_code_results():
    from agent.agent import _convert_messages_to_dict, _convert_dict_to_messages
    tool_calls = [{"name": "test", "args": {"x": 1}, "id": "c1", "type": "tool_call"}]
    original = [AIMessage(content="", tool_calls=tool_calls)]
    as_dict = _convert_messages_to_dict(original)
    assert as_dict == []


# ====== process_user_message（简单对话，不触发代码生成） ======

def test_process_user_message_simple_chat():
    from agent.agent import process_user_message

    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="你好！有什么需要的吗？")
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="你好",
            effect_id="",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert "你好" in result["response"]
    assert result["new_effect"] is None
    assert len(result["effect_messages"]) == 2  # user + assistant


# ====== process_user_message（触发代码生成） ======

_FAKE_CODE = """class Effect {
  static CONFIG = {
    size: { default: 20, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the circle size' },
  };
  constructor() { this.x = 0; }
  display(sketch, frameData, params) { sketch.ellipse(100, 100, params.size, 20); }
}"""


def test_process_user_message_with_code():
    from agent.agent import process_user_message

    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Create a red dot that follows the right wrist.",
            "requested_name": "Test Effect",
        },
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:

        from agent.schemas import CodeAgentResult
        mock_code.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="在右手画一个红色圆点",
            effect_id="",
            effect_messages=[],
            prev_code="",
            effect_name="测试效果",
            effect_list=[],
        )

    assert result["new_effect"] is not None
    assert result["new_effect"]["code"] == _FAKE_CODE
    assert result["new_effect"]["effect_name"] == "Test Effect"
    assert "size" in result["new_effect"]["params"]
    assert result["new_effect"]["params"]["size"] == 20
    assert result["response"] == (
        "Test Effect is ready.\n"
        "1 control available in Parameters."
    )
    assert "Controls the circle size" not in result["response"]


def test_pending_workspace_stays_create_and_keeps_its_id():
    """A pending workspace ID must not turn a creation request into an edit."""
    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult

    pending_id = "pending-workspace-123"
    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Create a violet glow around the left wrist.",
            "requested_name": "Violet Wrist Glow",
        },
        "id": "call_pending",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:
        mock_code.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="在左手腕周围加紫色光晕",
            thread_id=pending_id,
            effect_id=pending_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["thread_id"] == pending_id
    assert result["new_effect"]["effect_id"] == pending_id
    assert result["new_effect"]["effect_name"] == "Violet Wrist Glow"
    mock_code.assert_called_once_with(
        video_id="001",
        user_description="Create a violet glow around the left wrist.",
        prev_code="",
    )


def test_generation_save_preserves_name_and_params_changed_during_run():
    """A completed generation must merge code with newer direct user edits."""
    from agent import agent as agent_module
    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult

    effect_id = "concurrent-edit-123"
    agent_module._chat_manager.save_effect(
        effect_id,
        _FAKE_CODE,
        {"size": 20},
        "Original Name",
    )
    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Make the circle pulse.",
            "requested_name": "Original Name",
        },
        "id": "call_concurrent",
    }])

    def complete_generation(**kwargs):
        agent_module._chat_manager.patch_effect(
            effect_id,
            effect_name="Live Rename",
            parameter_updates={"size": 40},
        )
        return CodeAgentResult(status="submitted", code=_FAKE_CODE)

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:
        mock_code.side_effect = complete_generation
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="让它有脉冲效果",
            thread_id=effect_id,
            effect_id=effect_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["new_effect"]["effect_name"] == "Live Rename"
    assert result["new_effect"]["params"]["size"] == 40
    stored = agent_module._chat_manager.get_effect_detail(effect_id)
    assert stored["name"] == "Live Rename"
    assert stored["params"]["size"] == 40


def test_saved_effect_builds_code_free_trusted_edit_context():
    """Saved code enables edit mode without exposing source code to MainAgent."""
    from agent import agent as agent_module
    from agent.agent import process_user_message

    effect_id = "saved-effect-123"
    agent_module._chat_manager.save_effect(
        effect_id,
        _FAKE_CODE,
        {"size": 31},
        "Trusted Glow",
        status="draft",
    )

    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="I can update this effect.")
        mock_get.return_value = mock_llm

        process_user_message(
            video_id="001",
            user_input="把它改成蓝色",
            thread_id=effect_id,
            effect_id=effect_id,
            effect_messages=[],
            prev_code="untrusted frontend code",
            effect_name="Untrusted Name",
            effect_list=[],
        )

    messages = mock_llm.invoke.call_args.args[0]
    system_text = "\n".join(
        message.content for message in messages if isinstance(message, SystemMessage)
    )
    human_messages = [message.content for message in messages if isinstance(message, HumanMessage)]

    assert "[Operation: edit]" in system_text
    assert "[Current effect: name=Trusted Glow; status=draft]" in system_text
    assert '"size"' in system_text
    assert '"current": 31' in system_text
    assert "class Effect" not in system_text
    assert "untrusted frontend code" not in system_text
    assert human_messages[-1] == "把它改成蓝色"


def test_v2_checkpoint_bootstraps_only_visible_saved_history():
    """V2 ignores legacy checkpoints and restores code-free visible conversation."""
    from agent import agent as agent_module
    from agent.agent import process_user_message

    workspace_id = "legacy-workspace-123"
    agent_module._chat_manager.save_conversation(workspace_id, [
        {"role": "user", "content": "Create the original glow."},
        {"role": "assistant", "content": "The original glow is ready."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"name": "invoke_code_agent", "args": {}, "id": "old-call"}],
        },
        {
            "role": "tool",
            "content": "{'code': 'class Effect { display() {} }'}",
            "tool_call_id": "old-call",
        },
    ])

    legacy_graph = agent_module._get_main_graph()
    legacy_graph.update_state(
        {"configurable": {"thread_id": workspace_id}},
        {"messages": [AIMessage(content="class Effect { legacySecret() {} }")]},
    )

    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="What should change?")
        mock_get.return_value = mock_llm

        process_user_message(
            video_id="001",
            user_input="Make it softer.",
            thread_id=workspace_id,
            effect_id=workspace_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    messages = mock_llm.invoke.call_args.args[0]
    visible_text = "\n".join(
        str(message.content)
        for message in messages
        if isinstance(message, (HumanMessage, AIMessage))
    )

    assert "The original glow is ready." in visible_text
    assert "class Effect" not in visible_text
    assert not any(isinstance(message, ToolMessage) for message in messages)


def test_effect_mentions_are_resolved_from_active_backend_metadata():
    """Mention IDs are trusted only after active-effect resolution in storage."""
    from agent import agent as agent_module
    from agent.agent import process_user_message

    agent_module._chat_manager.save_effect(
        "active-reference",
        _FAKE_CODE,
        {"size": 20},
        "Stored Reference",
        status="active",
    )
    agent_module._chat_manager.save_effect(
        "draft-reference",
        _FAKE_CODE,
        {"size": 20},
        "Draft Reference",
        status="draft",
    )

    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="I found the reference.")
        mock_get.return_value = mock_llm

        process_user_message(
            video_id="001",
            user_input="参考我提到的效果",
            thread_id="pending-with-mention",
            effect_id="pending-with-mention",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[
                {"effect_id": "active-reference", "display_name": "Spoofed Name"},
                {"effect_id": "draft-reference", "display_name": "Draft Reference"},
            ],
        )

    messages = mock_llm.invoke.call_args.args[0]
    system_text = "\n".join(
        message.content for message in messages if isinstance(message, SystemMessage)
    )

    assert "Stored Reference" in system_text
    assert "active-reference" in system_text
    assert "Spoofed Name" not in system_text
    assert "Draft Reference" not in system_text


def test_trusted_context_is_replaced_with_latest_values_each_turn():
    """A continued V2 thread sees one current context message, not stale copies."""
    from agent.agent import process_user_message

    workspace_id = "changing-context-123"
    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            AIMessage(content="First reply."),
            AIMessage(content="Second reply."),
        ]
        mock_get.return_value = mock_llm

        common = {
            "video_id": "001",
            "thread_id": workspace_id,
            "effect_id": workspace_id,
            "effect_messages": [],
            "prev_code": "",
            "effect_name": "",
            "effect_list": [],
        }
        process_user_message(
            user_input="First turn.",
            pinned_joints={"p1": "left_wrist"},
            **common,
        )
        process_user_message(
            user_input="Second turn.",
            pinned_joints={"p1": "right_wrist"},
            **common,
        )

    second_messages = mock_llm.invoke.call_args_list[1].args[0]
    contexts = [
        message.content
        for message in second_messages
        if isinstance(message, SystemMessage)
        and message.content.startswith("## Trusted editor context")
    ]

    assert len(contexts) == 1
    assert "right_wrist" in contexts[0]
    assert "left_wrist" not in contexts[0]


def test_process_user_message_update_existing():
    """修改已有效果时，应沿用现有的 effect_id"""
    from agent import agent as agent_module
    from agent.agent import process_user_message

    existing_id = "existing-123"
    agent_module._chat_manager.save_effect(
        existing_id,
        _FAKE_CODE,
        {"size": 20},
        "Test Effect",
    )
    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Make the current geometry larger.",
            "requested_name": "Test Effect",
        },
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:

        from agent.schemas import CodeAgentResult
        mock_code.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="改大一点",
            effect_id=existing_id,
            effect_messages=[{"role": "assistant", "content": "已生成效果"}],
            prev_code=_FAKE_CODE,
            effect_name="测试效果",
            effect_list=[],
        )

    assert result["new_effect"] is not None
    assert result["new_effect"]["effect_id"] == existing_id  # 沿用旧 ID


def test_tool_node_uses_trusted_code_and_explicit_requested_name():
    """Edit code is trusted backend state while an explicit rename remains allowed."""
    from agent.agent import _tool_node

    state = {
        "messages": [AIMessage(content="", tool_calls=[{
            "name": "generate_effect",
            "args": {
                "user_description": "Change the circle to blue.",
                "requested_name": "Model Name",
            },
            "id": "call_1",
        }])],
        "main_action": {
            "action": "generate",
            "user_description": "Change the circle to blue.",
            "requested_name": "Model Name",
            "references": [],
            "parameter_updates": {},
        },
        "operation": "edit",
        "video_id": "trusted-video",
        "effect_id": "existing-123",
        "prev_code": _FAKE_CODE,
        "effect_name": "Trusted Name",
    }

    with patch("agent.agent.invoke_code_agent") as mock_tool:
        mock_tool.invoke.return_value = {
            "status": "submitted",
            "code": _FAKE_CODE,
            "params": {},
            "effect_name": "Trusted Name",
        }
        _tool_node(state)

    tool_args = mock_tool.invoke.call_args.args[0]
    assert tool_args["video_id"] == "trusted-video"
    assert tool_args["prev_code"] == _FAKE_CODE
    assert tool_args["effect_name"] == "Model Name"


def test_tool_node_preserves_controls_named_only_in_raw_user_input():
    """MainAgent paraphrasing cannot remove the hard binding requirement."""
    from agent.agent import _tool_node

    editor_context = {
        "effect_id": "workspace-time",
        "video_id": "trusted-video",
        "editor_revision": 1,
        "editor_state": {
            "schema_version": 2,
            "video_id": "trusted-video",
            "active_interval": {"start_frame": 0, "end_frame": 200},
            "points": [],
            "markers": [
                {"id": "marker-1", "alias": "t1", "frame": 34},
                {"id": "marker-2", "alias": "t2", "frame": 121},
            ],
            "next_alias": {"point": 1, "marker": 3},
        },
        "selection": {"current_frame": 50, "selected_point_id": None},
    }
    state = {
        "messages": [AIMessage(content="", tool_calls=[{
            "name": "generate_effect",
            "args": {
                "user_description": "Animate during the selected interval.",
                "requested_name": "Timed Effect",
            },
            "id": "call_time",
        }])],
        "main_action": {
            "action": "generate",
            "user_description": "Animate during the selected interval.",
            "requested_name": "Timed Effect",
            "references": [],
            "parameter_updates": {},
        },
        "user_input": "Animate a star from t1 to t2.",
        "operation": "create",
        "video_id": "trusted-video",
        "effect_id": "workspace-time",
        "prev_code": "",
        "effect_name": "",
        "editor_context": editor_context,
    }

    with patch("agent.agent.invoke_code_agent") as mock_tool:
        mock_tool.invoke.return_value = {
            "status": "submitted",
            "code": _FAKE_CODE,
            "params": {},
            "effect_name": "Timed Effect",
        }
        _tool_node(state)

    tool_args = mock_tool.invoke.call_args.args[0]
    assert tool_args["required_control_ids"] == ["marker-1", "marker-2"]


def test_process_user_message_no_code_returned():
    """当 CodeAgent 返回空代码时，不应创建 new_effect"""
    from agent.agent import process_user_message

    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {"user_description": "Create a test glow.", "requested_name": "Test"},
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:

        from agent.schemas import CodeAgentResult
        mock_code.return_value = CodeAgentResult(
            status="failed", reason="模型未提交代码就结束"
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001", user_input="测试", effect_id="",
            effect_messages=[], prev_code="", effect_name="",
            effect_list=[],
        )

    assert result["new_effect"] is None


def test_process_user_message_failed_saves_draft():
    """CodeAgent 失败但留有校验代码 → 保存为草稿并如实说明"""
    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult

    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {"user_description": "Create a test glow.", "requested_name": "Test"},
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:

        mock_code.return_value = CodeAgentResult(
            status="failed", reason="验证未通过", last_validated_code=_FAKE_CODE
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001", user_input="测试", effect_id="",
            effect_messages=[], prev_code="", effect_name="测试",
            effect_list=[],
        )

    assert result["new_effect"] is not None
    assert result["new_effect"]["status"] == "draft"
    assert result["new_effect"]["code"] == _FAKE_CODE
    assert "draft" in result["response"]


def test_failed_generation_with_invalid_control_bindings_does_not_crash_draft_save():
    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult

    invalid_binding_code = _FAKE_CODE.replace(
        "static CONFIG = {",
        "static CONTROL_BINDINGS = { timeMarkers: { event: { type: 'time_marker', id: 'marker-1' } } };\n  static CONFIG = {",
    )
    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {"user_description": "Create a timed glow.", "requested_name": "Timed Glow"},
        "id": "call_invalid_draft",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:
        mock_code.return_value = CodeAgentResult(
            status="failed",
            reason="Hard validation failed",
            last_validated_code=invalid_binding_code,
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001",
            user_input="Create a timed glow.",
            effect_id="invalid-binding-draft",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["new_effect"] is None
    assert result["response"] == (
        "I could not create a usable effect after validation. "
        "Please simplify or rephrase the visual behavior and retry."
    )


def test_failed_edit_preserves_the_existing_active_effect():
    from agent import agent as agent_module
    from agent.schemas import CodeAgentResult

    effect_id = "active-edit-failure"
    agent_module._chat_manager.save_effect(
        effect_id,
        _FAKE_CODE,
        {"size": 20},
        "Working Effect",
    )
    failed_candidate = _FAKE_CODE.replace("#FF00AA", "#00AAFF")
    model_action = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {
            "user_description": "Change the Effect to blue.",
            "requested_name": "Working Effect",
        },
        "id": "call_failed_edit",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:
        mock_code.return_value = CodeAgentResult(
            status="failed",
            reason="Hard validation failed",
            last_validated_code=failed_candidate,
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = model_action
        mock_get.return_value = mock_llm

        result = agent_module.process_user_message(
            video_id="video-1",
            user_input="改成蓝色",
            thread_id=effect_id,
            effect_id=effect_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["new_effect"] is None
    assert result["response"] == (
        "The current Effect was not changed because the generated edit did not pass "
        "validation. Its existing active version is still available."
    )
    stored = agent_module._chat_manager.effects.get(effect_id)
    assert stored.status == "active"
    assert stored.code == _FAKE_CODE
    assert stored.params == {"size": 20}


def test_process_user_message_failed_no_code():
    """CodeAgent 失败且无任何代码 → 不保存效果，如实告知失败原因"""
    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult

    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {"user_description": "Create a test glow.", "requested_name": "Test"},
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code:

        mock_code.return_value = CodeAgentResult(
            status="failed", reason="The model ended without submitting code"
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        result = process_user_message(
            video_id="001", user_input="测试", effect_id="",
            effect_messages=[], prev_code="", effect_name="",
            effect_list=[],
        )

    assert result["new_effect"] is None
    assert "could not create a usable effect" in result["response"]


def test_process_user_message_failed_saves_error_conversation():
    """失败时对话应持久化，且最后一条助手消息带 isError，供前端重试"""
    import tempfile

    from agent.agent import process_user_message
    from agent.schemas import CodeAgentResult
    from chat_manager import ChatManager

    tmpdir = tempfile.TemporaryDirectory()
    cm = ChatManager(data_dir=tmpdir.name)

    mock_response = AIMessage(content="", tool_calls=[{
        "name": "generate_effect",
        "args": {"user_description": "Create a test glow.", "requested_name": "Test"},
        "id": "call_1",
    }])

    with patch("agent.llm.get_main_agent_llm") as mock_get, \
         patch("agent.tools.code_agent_module.invoke_code_agent") as mock_code, \
         patch("agent.agent._chat_manager", cm):

        mock_code.return_value = CodeAgentResult(
            status="failed", reason="模型未提交代码就结束"
        )
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get.return_value = mock_llm

        process_user_message(
            video_id="001", user_input="测试", effect_id="effect-fail",
            effect_messages=[], prev_code="", effect_name="",
            effect_list=[],
        )

    conv = cm.get_conversation("effect-fail")
    assert conv, "失败对话应被持久化"
    assert conv[0]["role"] == "user"
    assert conv[0]["content"] == "测试"
    assert conv[-1]["role"] == "assistant"
    assert conv[-1].get("isError") is True
    tmpdir.cleanup()


def test_process_user_message_multi_turn_thread():
    """后端持有状态：第二轮只传 thread_id + 新消息，上下文仍连续"""
    from agent.agent import process_user_message

    with patch("agent.llm.get_main_agent_llm") as mock_get:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            AIMessage(content="你好！我是助手。"),
            AIMessage(content="好的，继续。"),
        ]
        mock_get.return_value = mock_llm

        r1 = process_user_message(
            video_id="001", user_input="你好", effect_id="",
            effect_messages=[], prev_code="", effect_name="", effect_list=[],
        )
        tid = r1["thread_id"]
        assert tid

        # 第二轮不传历史，只传 thread_id
        r2 = process_user_message(
            video_id="001", user_input="继续", effect_id="",
            thread_id=tid, effect_messages=[], prev_code="", effect_name="", effect_list=[],
        )

    assert r2["thread_id"] == tid
    # user + assistant + user + assistant = 4 条，说明上一轮上下文被恢复
    assert len(r2["effect_messages"]) >= 4
