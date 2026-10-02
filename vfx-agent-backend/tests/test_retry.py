"""外层有界重试测试（Mock CodeAgent，避免真实 LLM 调用）"""

from unittest.mock import patch

from agent.tools import invoke_code_agent
from agent.schemas import CodeAgentResult


_FAKE_CODE = """class Effect {
  static CONFIG = {
    size: { default: 20, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the circle size' },
  };
  constructor() { this.x = 0; }
  display(sketch, frameData, params) { sketch.ellipse(100, 100, params.size, 20); }
}"""


def _invoke():
    return invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "红色圆点",
        "effect_name": "测试效果",
    })


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_no_retry_on_success(mock_invoke):
    """一次成功：只调用 1 次，不重试"""
    mock_invoke.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

    result = _invoke()

    assert result["status"] == "submitted"
    assert result["code"] == _FAKE_CODE
    assert result["reason"] == ""
    mock_invoke.assert_called_once()


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_retry_once_then_success(mock_invoke):
    """第一次失败、第二次成功：只重试 1 次，第二次带原因且用修复模式"""
    mock_invoke.side_effect = [
        CodeAgentResult(status="failed", reason="语法错误", last_validated_code=_FAKE_CODE),
        CodeAgentResult(status="submitted", code=_FAKE_CODE),
    ]

    result = _invoke()

    assert result["status"] == "submitted"
    assert mock_invoke.call_count == 2
    second_kwargs = mock_invoke.call_args.kwargs
    assert "语法错误" in second_kwargs["user_description"]
    assert second_kwargs["prev_code"] == _FAKE_CODE


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_retry_exhausted_and_reason_not_stacked(mock_invoke):
    """三次全失败：共调用 3 次；每次重试只带最新原因，不叠加历史原因"""
    mock_invoke.side_effect = [
        CodeAgentResult(status="failed", reason="原因A", last_validated_code=_FAKE_CODE),
        CodeAgentResult(status="failed", reason="原因B", last_validated_code=_FAKE_CODE),
        CodeAgentResult(status="failed", reason="原因C", last_validated_code=_FAKE_CODE),
    ]

    result = _invoke()

    assert mock_invoke.call_count == 3
    assert result["status"] == "failed"
    assert result["reason"] == "原因C"
    assert result["code"] == ""
    assert result["last_validated_code"] == _FAKE_CODE

    # 第 2 次调用（第 1 次重试）：带原因A，不带原因B
    first_retry_kwargs = mock_invoke.call_args_list[1].kwargs
    assert "原因A" in first_retry_kwargs["user_description"]
    assert "原因B" not in first_retry_kwargs["user_description"]

    # 第 3 次调用（第 2 次重试）：只带原因B，不叠加原因A
    second_retry_kwargs = mock_invoke.call_args_list[2].kwargs
    assert "原因B" in second_retry_kwargs["user_description"]
    assert "原因A" not in second_retry_kwargs["user_description"]


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_retry_regenerates_when_no_code(mock_invoke):
    """失败且没有 last_validated_code：重试时 prev_code 为空（重写模式）"""
    mock_invoke.side_effect = [
        CodeAgentResult(status="failed", reason="模型未提交代码就结束"),
        CodeAgentResult(status="submitted", code=_FAKE_CODE),
    ]

    result = _invoke()

    assert result["status"] == "submitted"
    assert mock_invoke.call_count == 2
    assert mock_invoke.call_args.kwargs["prev_code"] == ""


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_retry_keeps_original_prev_code_when_no_validated_code(mock_invoke):
    """修改模式失败但没有新代码：重试时用原始 prev_code 作为修复基础"""
    mock_invoke.side_effect = [
        CodeAgentResult(status="failed", reason="修改失败"),
        CodeAgentResult(status="submitted", code=_FAKE_CODE),
    ]

    result = invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "改成蓝色",
        "prev_code": "旧代码",
        "effect_name": "测试效果",
    })

    assert result["status"] == "submitted"
    assert mock_invoke.call_count == 2
    assert mock_invoke.call_args.kwargs["prev_code"] == "旧代码"
