"""集成测试：调用真实 LLM 走一次完整 ReAct 循环"""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid
import pytest

from langchain_core.messages import SystemMessage, HumanMessage

from agent.code_agent import build_code_agent_graph
from agent.schemas import CodeAgentState
from agent.prompts import CODE_AGENT_SYSTEM, FRAMEWORK_CONSTRAINTS, PRIVATE_CONVENTIONS
from config import CODE_AGENT_MODEL

pytestmark = pytest.mark.live


def test_code_generation(log_path: str = ""):
    effect_id = str(uuid.uuid4())
    log_file = Path(log_path) if log_path else (
        Path(__file__).resolve().parents[1]
        / "logs"
        / f"reasoning_{effect_id[:8]}.txt"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    user_description = "双手移动时，路径会留下一根发光的彩色轨迹线，颜色从蓝色慢慢变成紫色。移动速度慢时，轨迹会聚成柔和的光晕；移动速度快时，轨迹会炸开成许多细小的光点，并拖着淡淡的尾巴消散。"

    initial_state = CodeAgentState(
        video_id="001",
        user_description=user_description,
        prev_code="",
        max_soft_fixes=2,
        max_hard_fixes=3,
        soft_fix_count=0,
        hard_fix_count=0,
        soft_validation_bypassed=False,
        effect_list=[],
        pose_stats={},
        todo=[],
        rounds_since_todo=0,
        code="",
        last_validated_code="",
        validate_result={},
        messages=[
            SystemMessage(content=CODE_AGENT_SYSTEM + "\n\n" + FRAMEWORK_CONSTRAINTS + "\n\n" + PRIVATE_CONVENTIONS),
            HumanMessage(content=f"Video ID: 001\n\n{user_description}"),
        ],
    )

    graph = build_code_agent_graph()
    round_idx = 0
    total_start = time.time()
    round_start = total_start

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
                        log(f"  → 调用工具: {tc['name']}({tc['args']})")
                log(f"{'='*60}")
                round_start = time.time()

            elif node_name == "tools":
                round_time = time.time() - round_start
                elapsed = time.time() - total_start
                log(f"  [工具返回] ({round_time:.1f}s, 累计 {elapsed:.1f}s) {msg.content[:500]}")

    total_time = time.time() - total_start

    final_state = graph.get_state({"configurable": {"thread_id": effect_id}})
    vals = final_state.values

    log(f"\n{'='*60}")
    log("【最终结果】")
    code = vals.get("code", "")
    log(f"code ({len(code)} chars):")
    log(code if code else "(空)")
    log(f"{'='*60}")

    log(f"\n总耗时: {total_time:.1f}s  |  共 {round_idx} 轮  |  code: {len(code)} chars")
    log(f"(日志已保存到: {log_path})")

    assert code, "代码为空"


if __name__ == "__main__":
    test_code_generation()
