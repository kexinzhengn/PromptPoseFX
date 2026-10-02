"""主 Agent 集成测试：调用真实 LLM，端到端验证全流程"""

import uuid
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from agent.agent import process_user_message
from agent.hard_validate import hard_validate_effect
from chat_manager import ChatManager

pytestmark = pytest.mark.live


def _isolated_cm():
    """创建一个隔离的 ChatManager（测试数据不污染真实存储）"""
    tmpdir = tempfile.TemporaryDirectory()
    cm = ChatManager(data_dir=tmpdir.name)
    return cm, tmpdir


def test_simple_chat():
    """简单对话：不应触发代码生成，回复应有内容"""
    cm, tmp = _isolated_cm()
    with patch("agent.agent._chat_manager", cm):
        result = process_user_message(
            video_id="001",
            user_input="你好，请简单介绍一下你自己",
            effect_id="",
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    assert result["response"], "回复不应为空"
    assert result["new_effect"] is None, "简单对话不应生成效果"
    assert len(result["effect_messages"]) >= 2  # user + assistant
    tmp.cleanup()


def _FAKE_CODE():
    return """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: { default: 25, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the circle size' },
  };
  constructor() {}
  display(sketch, frameData, params) {
    const s = params.size;
    sketch.ellipse(100, 100, s, s);
  }
}"""


def test_code_generation():
    """触发代码生成：可能先返回选项，选择后生成效果"""
    cm, tmp = _isolated_cm()
    with patch("agent.agent._chat_manager", cm):
        result = process_user_message(
            video_id="001",
            user_input="在右手腕画一个红色的圆，跟随着手腕移动",
            effect_id="",
            effect_messages=[],
            prev_code="",
            effect_name="红色圆圈",
            effect_list=[],
        )

    assert result["response"], "回复不应为空"

    # 新行为：Agent 可能先返回选项让用户细化需求
    if result.get("options"):
        assert result["options_header"], "有选项时应有 header"
        assert 2 <= len(result["options"]) <= 4, "选项应在 2-4 个"
        # 选择第一个选项继续
        selected = result["options"][0]
        follow_up = selected["label"]
        ne = result.get("new_effect") or {}
        with patch("agent.agent._chat_manager", cm):
            result = process_user_message(
                video_id="001",
                user_input=follow_up,
                selected_option_id=selected["id"],
                thread_id=result["thread_id"],
                effect_id=ne.get("effect_id", result["thread_id"]),
                effect_messages=result["effect_messages"],
                prev_code=ne.get("code", ""),
                effect_name=ne.get("effect_name", "红色圆圈"),
                effect_list=[],
            )

    assert result["new_effect"] is not None, "应生成新效果"

    ne = result["new_effect"]
    assert ne["code"], "代码不应为空"
    assert "class Effect" in ne["code"], "代码应包含 class Effect"
    assert ne["effect_name"], "效果名不应为空"
    assert ne["effect_id"], "效果 ID 不应为空"
    assert isinstance(ne["params"], dict), "params 应为 dict"

    # 验证 chat_manager 已保存
    detail = cm.get_effect_detail(ne["effect_id"])
    assert detail is not None, "chat_manager 应能读取到效果"
    assert detail["code"] == ne["code"]
    assert detail["name"] == ne["effect_name"]

    print(f"\n集成测试通过: {ne['effect_name']} | code={len(ne['code'])}B | params={ne['params']}")
    tmp.cleanup()


def test_code_generation_with_effect_list():
    """有效果列表上下文时仍能正常生成，兼容选项交互"""
    cm, tmp = _isolated_cm()
    existing_id = str(uuid.uuid4())
    cm.save_effect(existing_id, _FAKE_CODE(), {"size": 30}, "参考效果")

    with patch("agent.agent._chat_manager", cm):
        result = process_user_message(
            video_id="001",
            user_input="在右手腕画一个蓝色圆点",
            effect_id="",
            effect_messages=[],
            prev_code="",
            effect_name="蓝色圆点",
            effect_list=[{"id": existing_id, "name": "参考效果"}],
        )

    # 新行为：Agent 可能先返回选项
    if result.get("options"):
        selected = result["options"][0]
        follow_up = selected["label"]
        with patch("agent.agent._chat_manager", cm):
            result = process_user_message(
                video_id="001",
                user_input=follow_up,
                selected_option_id=selected["id"],
                thread_id=result["thread_id"],
                effect_id=result["thread_id"],
                effect_messages=result["effect_messages"],
                prev_code="",
                effect_name="蓝色圆点",
                effect_list=[{"id": existing_id, "name": "参考效果"}],
            )

    assert result["new_effect"] is not None, "应生成新效果"
    assert "Effect" in result["new_effect"]["code"]
    tmp.cleanup()


def test_modify_existing_effect():
    """修改已有效果：应沿用同一 effect_id，兼容选项交互"""
    cm, tmp = _isolated_cm()
    existing_id = str(uuid.uuid4())
    cm.save_effect(existing_id, _FAKE_CODE(), {"size": 25}, "红色圆圈")

    with patch("agent.agent._chat_manager", cm):
        result = process_user_message(
            video_id="001",
            user_input="把圆改成蓝色",
            effect_id=existing_id,
            effect_messages=[
                {"role": "assistant", "content": "已生成红色圆圈"},
            ],
            prev_code=_FAKE_CODE(),
            effect_name="蓝色圆圈",
            effect_list=[{"id": existing_id, "name": "红色圆圈"}],
        )

    # 新行为：Agent 可能先返回选项
    if result.get("options"):
        selected = result["options"][0]
        follow_up = selected["label"]
        with patch("agent.agent._chat_manager", cm):
            result = process_user_message(
                video_id="001",
                user_input=follow_up,
                selected_option_id=selected["id"],
                thread_id=existing_id,
                effect_id=existing_id,
                effect_messages=result["effect_messages"],
                prev_code=_FAKE_CODE(),
                effect_name="蓝色圆圈",
                effect_list=[{"id": existing_id, "name": "红色圆圈"}],
            )

    assert result["new_effect"] is not None, "修改应返回新效果"
    assert result["new_effect"]["effect_id"] == existing_id, "修改应沿用原 effect_id"

    detail = cm.get_effect_detail(existing_id)
    assert detail is not None
    print(f"\n修改测试通过: 沿用 effect_id={existing_id[:8]}...")
    tmp.cleanup()


def test_parameter_update_uses_real_main_agent_without_code_generation():
    """A matching CONFIG control must use the direct repository update path."""
    cm, tmp = _isolated_cm()
    effect_id = str(uuid.uuid4())
    original_code = _FAKE_CODE()
    cm.save_effect(effect_id, original_code, {"size": 25}, "Wrist Circle")

    with patch("agent.agent._chat_manager", cm), \
         patch("agent.agent.invoke_code_agent", new=MagicMock()) as code_agent:
        result = process_user_message(
            video_id="001",
            user_input="把大小调到40",
            thread_id=effect_id,
            effect_id=effect_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
        )

    code_agent.assert_not_called()
    assert result["new_effect"] is None
    assert result["effect_update"]["params"]["size"] == 40
    assert cm.get_effect_detail(effect_id)["code"] == original_code
    tmp.cleanup()


def test_explicit_reference_generation_passes_real_pose_hard_validation(
    pose_timeline_path,
):
    """An explicit active reference must reach a generated, hard-valid Effect."""
    cm, tmp = _isolated_cm()
    reference_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    cm.save_effect(
        reference_id,
        _FAKE_CODE(),
        {"size": 25},
        "Reference Wrist Circle",
        status="active",
    )

    with patch("agent.agent._chat_manager", cm):
        result = process_user_message(
            video_id="001",
            user_input=(
                "Reference @Reference Wrist Circle's clean circular anchor behavior "
                "to create a cyan pulse on the right wrist."
            ),
            thread_id=workspace_id,
            effect_id=workspace_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            effect_mentions=[{
                "effect_id": reference_id,
                "display_name": "Reference Wrist Circle",
            }],
        )

    assert result["new_effect"] is not None
    assert result["new_effect"]["status"] == "active"
    stored = cm.get_effect_detail(workspace_id)
    references = stored["generation_metadata"]["references"]
    assert [reference["effect_id"] for reference in references] == [reference_id]
    assert "anchor" in references[0]["reference_intent"].casefold()
    validation = hard_validate_effect(result["new_effect"]["code"], pose_timeline_path)
    assert validation.passed, validation.errors
    tmp.cleanup()
