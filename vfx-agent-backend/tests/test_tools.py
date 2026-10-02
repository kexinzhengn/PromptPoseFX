"""主 Agent 工具测试（Mock CodeAgent，避免真实 LLM 调用）"""

import json
from unittest.mock import patch, MagicMock

from agent.tools import invoke_code_agent
from agent.schemas import CodeAgentResult


# 一段包含 CONFIG 的假代码，extract_config 能提取出 params
_FAKE_CODE = """class Effect {
  static CONFIG = {
    size: { default: 20, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the circle size' },
    color: { default: '#ff0000', type: 'color', label: 'Color', description: 'Controls the circle color' },
  };
  constructor() { this.x = 0; }
  display(sketch, frameData, params) {
    const s = params.size;
    sketch.ellipse(100, 100, s, s);
  }
}"""


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_invoke_code_agent(mock_invoke):
    """invoke_code_agent 应返回 code + params + effect_name"""
    mock_invoke.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

    result = invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "红色圆点",
        "effect_name": "测试效果",
    })

    assert result["code"] == _FAKE_CODE
    assert result["effect_name"] == "测试效果"
    assert "params" in result
    assert result["params"]["size"] == 20
    assert result["params"]["color"] == "#ff0000"


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_invoke_code_agent_empty_code(mock_invoke):
    """当 CodeAgent 返回空代码时，tool 应返回空"""
    mock_invoke.return_value = CodeAgentResult(
        status="failed", reason="模型未提交代码就结束"
    )

    result = invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "空",
        "effect_name": "空效果",
    })

    assert result["code"] == ""
    assert result["params"] == {}
    assert result["effect_name"] == "空效果"


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_invoke_code_agent_no_config(mock_invoke):
    """代码里没有 CONFIG 时，params 应为空"""
    code_no_config = "class Effect { constructor() {} display() { ellipse(10,10,10,10); } }"
    mock_invoke.return_value = CodeAgentResult(status="submitted", code=code_no_config)

    result = invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "简单形状",
        "effect_name": "无参数",
    })

    assert result["code"] == code_no_config
    assert result["params"] == {}  # 无 CONFIG 则空


@patch("agent.tools.code_agent_module.invoke_code_agent")
def test_invoke_code_agent_calls_code_agent(mock_invoke):
    """验证工具正确传递了 video_id 和 user_description 给 CodeAgent"""
    mock_invoke.return_value = CodeAgentResult(status="submitted", code=_FAKE_CODE)

    invoke_code_agent.invoke({
        "video_id": "001",
        "user_description": "测试",
        "prev_code": "",
        "effect_name": "测试",
    })

    mock_invoke.assert_called_once_with(
        video_id="001",
        user_description="测试",
        prev_code="",
    )
