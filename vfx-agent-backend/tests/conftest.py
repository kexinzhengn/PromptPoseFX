import sys
import os
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# 把项目根目录加到 sys.path，让 from agent import ... 能工作
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolated_chat_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Give every test isolated Effect storage and LangGraph checkpoints."""
    import config
    from chat_manager import ChatManager

    with tempfile.TemporaryDirectory(prefix="promptposefx_pytest_chat_") as temp_dir:
        storage_path = Path(temp_dir)
        pose_data_dir = storage_path / "pose_data"
        pose_path = pose_data_dir / "001" / "smoothed_landmark.json"
        pose_path.parent.mkdir(parents=True)
        pose_path.write_text(
            json.dumps({
                str(frame): [
                    [100 + frame * 12 + joint, 120 + frame * 3 + joint]
                    for joint in range(33)
                ]
                for frame in range(180)
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "CHAT_DATA_DIR", str(storage_path))
        monkeypatch.setattr(config, "CHECKPOINT_DB", str(storage_path / "langgraph.db"))
        monkeypatch.setattr(config, "POSE_DATA_DIR", str(pose_data_dir))

        code_tools_module = sys.modules.get("agent.code_tools")
        if code_tools_module is not None:
            monkeypatch.setattr(code_tools_module, "POSE_DATA_DIR", str(pose_data_dir))

        manager = ChatManager(data_dir=str(storage_path))
        for module_name in ("agent.agent", "agent.tools", "app"):
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "_chat_manager"):
                monkeypatch.setattr(module, "_chat_manager", manager)
        agent_module = sys.modules.get("agent.agent")
        if agent_module is not None:
            checkpointer = getattr(getattr(agent_module, "_main_graph", None), "checkpointer", None)
            connection = getattr(checkpointer, "conn", None)
            if connection is not None:
                connection.close()
            agent_module._main_graph = None
            monkeypatch.setattr(agent_module, "CHECKPOINT_DB", str(storage_path / "langgraph.db"))

        yield storage_path

        agent_module = sys.modules.get("agent.agent")
        if agent_module is not None:
            checkpointer = getattr(getattr(agent_module, "_main_graph", None), "checkpointer", None)
            connection = getattr(checkpointer, "conn", None)
            if connection is not None:
                connection.close()
            agent_module._main_graph = None

    assert not storage_path.exists()


@pytest.fixture
def pose_timeline_path(isolated_chat_storage: Path) -> Path:
    """Return the synthetic Pose timeline created for offline tests."""
    return isolated_chat_storage / "pose_data" / "001" / "smoothed_landmark.json"
