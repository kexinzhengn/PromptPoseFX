"""参考：修改已有代码的集成测试"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import SystemMessage, HumanMessage

from agent.code_agent import build_code_agent_graph
from agent.schemas import CodeAgentState
from agent.prompts import CODE_AGENT_SYSTEM, FRAMEWORK_CONSTRAINTS, PRIVATE_CONVENTIONS

pytestmark = pytest.mark.live


def _load_fixture(filename: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_modify_existing_code(log_path: str = ""):
    """加载已有代码，让 LLM 做简单修改"""
    fixture = _load_fixture("sample_effect_glow.json")
    prev_code = fixture["code"]
    prev_name = fixture["effect_name"]

    effect_id = str(uuid.uuid4())
    log_file = Path(log_path) if log_path else (
        Path(__file__).resolve().parents[1]
        / "logs"
        / f"modify_{effect_id[:8]}.txt"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    # 简单修改：只改颜色
    user_description = f"把颜色从蓝色改成红色，其他不变。当前效果名：{prev_name}"

    initial_state = CodeAgentState(
        video_id="001",
        user_description=user_description,
        prev_code=prev_code,
        max_soft_fixes=2,
        max_hard_fixes=3,
        soft_fix_count=0,
        hard_fix_count=0,
        soft_validation_bypassed=False,
        submitted=False,
        effect_list=[],
        pose_stats={},
        todo=[],
        rounds_since_todo=0,
        code="",
        last_validated_code="",
        validate_result={},
        messages=[
            SystemMessage(content=CODE_AGENT_SYSTEM + "\n\n" + FRAMEWORK_CONSTRAINTS + "\n\n" + PRIVATE_CONVENTIONS),
            HumanMessage(content=f"Video ID: 001\n\n{user_description}\n\nModify the following existing code:\n{prev_code}"),
        ],
    )

    graph = build_code_agent_graph()
    round_idx = 0
    total_start = time.time()

    for step in graph.stream(initial_state, config={"configurable": {"thread_id": effect_id}}):
        for node_name, state_update in step.items():
            msgs = state_update.get("messages", [])
            if not msgs:
                continue
            msg = msgs[-1]

            if node_name == "agent":
                round_idx += 1
                elapsed = time.time() - total_start
                log(f"\n{'='*60}")
                log(f"【第 {round_idx} 轮 — Agent 思考】（累计 {elapsed:.1f}s）")
                if msg.content:
                    log(msg.content[:600])
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        args = str(tc["args"])
                        log(f"  → 调用工具: {tc['name']}({args[:150]})")
                log(f"{'='*60}")

            elif node_name == "tools":
                elapsed = time.time() - total_start
                log(f"  [工具返回] (累计 {elapsed:.1f}s) {msg.content[:500]}")

    total_time = time.time() - total_start

    final_state = graph.get_state({"configurable": {"thread_id": effect_id}})
    vals = final_state.values

    log(f"\n{'='*60}")
    log("【最终结果】")
    code = vals.get("code", "")
    log(f"code ({len(code)} chars):")
    log(code[:500] + "..." if len(code) > 500 else code)
    log(f"{'='*60}")

    log(f"\n总耗时: {total_time:.1f}s  |  共 {round_idx} 轮  |  code: {len(code)} chars")
    log(f"(日志已保存到: {log_path})")

    assert code, "代码为空"
    assert code != prev_code, "代码未发生变化"


if __name__ == "__main__":
    test_modify_existing_code()
