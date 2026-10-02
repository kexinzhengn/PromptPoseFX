"""RunManager 测试：run 生命周期、事件日志、SSE 回放"""

import json
import os
import tempfile
import time

from editor_controls import EditorContextSnapshot, EditorSelection, empty_editor_state
from run_manager import RunManager, RunBusyError
from agent.events import RunCancelled


def _make_mgr():
    """创建使用临时数据库的 RunManager"""
    tmpdir = tempfile.TemporaryDirectory()
    return RunManager(db_path=os.path.join(tmpdir.name, "runs.db")), tmpdir


def test_create_run_status_running():
    mgr, tmp = _make_mgr()
    rid = mgr.create_run("thread_1")
    run = mgr.get_run(rid)
    assert run is not None
    assert run["status"] == "running"
    assert run["thread_id"] == "thread_1"
    tmp.cleanup()


def test_append_and_get_events_in_order():
    mgr, tmp = _make_mgr()
    rid = mgr.create_run("thread_1")
    mgr.append_event(rid, "stage", {"stage": "thinking", "content": "理解需求"})
    mgr.append_event(rid, "tool", {"tool": "validate", "status": "fail", "detail": {"issues": 2}})
    events = mgr.get_events(rid)
    assert [e["type"] for e in events] == ["stage", "tool"]
    assert events[0]["stage"] == "thinking"
    assert events[1]["tool"] == "validate"
    tmp.cleanup()


def test_terminal_updates_run_status():
    mgr, tmp = _make_mgr()
    rid = mgr.create_run("thread_1")
    mgr.append_event(rid, "terminal", {"status": "succeeded", "result": {"response": "ok"}})
    assert mgr.get_run(rid)["status"] == "succeeded"
    assert mgr.get_events(rid)[-1]["type"] == "terminal"
    tmp.cleanup()


def test_event_stream_replays_history_then_closes():
    """订阅时先回放已有事件，遇到 terminal 后关闭流"""
    mgr, tmp = _make_mgr()
    rid = mgr.create_run("thread_1")
    mgr.append_event(rid, "stage", {"stage": "generating", "content": "生成中"})
    mgr.append_event(rid, "terminal", {"status": "succeeded", "result": {"response": "完成"}})

    chunks = list(mgr.event_stream(rid))
    events = [json.loads(chunk.split("data: ", 1)[1]) for chunk in chunks]

    assert [e["type"] for e in events] == ["stage", "terminal"]
    assert events[0]["stage"] == "generating"
    assert events[-1]["status"] == "succeeded"
    tmp.cleanup()


def test_get_run_missing():
    mgr, tmp = _make_mgr()
    assert mgr.get_run("不存在的run") is None
    tmp.cleanup()


# ====== 取消 / busy / 存档点 ======

def _fake_runner(result=None, wait_cancel=False):
    """测试用 runner：wait_cancel=True 时阻塞直到取消，否则直接返回 result"""
    def runner(run_id, thread_id, video_id, user_input, pinned_joints,
               cancel_event, resume_checkpoint_id, on_event, on_tool_event):
        if wait_cancel:
            while not cancel_event.is_set():
                time.sleep(0.01)
            raise RunCancelled("任务已取消")
        return result if result is not None else {"response": "ok", "checkpoint_id": "cp1"}
    return runner


def _wait_status(mgr, run_id, timeout=5.0):
    """等待 run 离开 running 状态，返回最终状态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = mgr.get_run(run_id)
        if run and run["status"] != "running":
            return run["status"]
        time.sleep(0.02)
    return mgr.get_run(run_id)["status"] if mgr.get_run(run_id) else None


def test_busy_rejects_second_run_on_same_thread():
    mgr, tmp = _make_mgr()
    rid = mgr.start("t1", "v1", "第一条", {}, runner=_fake_runner(wait_cancel=True))
    try:
        mgr.start("t1", "v1", "第二条", {}, runner=_fake_runner())
        assert False, "同一线程应拒绝并发任务"
    except RunBusyError:
        pass
    mgr.cancel(rid)
    assert _wait_status(mgr, rid) == "cancelled"
    tmp.cleanup()


def test_cancel_marks_run_cancelled():
    mgr, tmp = _make_mgr()
    rid = mgr.start("t1", "v1", "慢任务", {}, runner=_fake_runner(wait_cancel=True))
    assert mgr.get_run(rid)["status"] == "running"
    assert mgr.cancel(rid) is True
    assert _wait_status(mgr, rid) == "cancelled"
    events = mgr.get_events(rid)
    assert events[-1]["type"] == "terminal"
    assert events[-1]["status"] == "cancelled"
    tmp.cleanup()


def test_cancel_missing_returns_false():
    mgr, tmp = _make_mgr()
    assert mgr.cancel("不存在的run") is False
    tmp.cleanup()


def test_success_stores_checkpoint_id():
    mgr, tmp = _make_mgr()
    rid = mgr.start(
        "t1", "v1", "任务", {},
        runner=_fake_runner(result={"response": "ok", "checkpoint_id": "cp-123"}),
    )
    assert _wait_status(mgr, rid) == "succeeded"
    assert mgr._checkpoint_map.get("t1") == "cp-123"
    tmp.cleanup()


def test_start_passes_effect_mentions_to_supported_runner():
    """Structured mentions reach the agent runner without trusting display text."""
    mgr, tmp = _make_mgr()
    received = {}

    def runner(
        run_id,
        thread_id,
        video_id,
        user_input,
        pinned_joints,
        effect_mentions,
        cancel_event,
        resume_checkpoint_id,
        on_event,
        on_tool_event,
    ):
        received["effect_mentions"] = effect_mentions
        return {"response": "ok", "checkpoint_id": "cp-mentions"}

    mentions = [{"effect_id": "reference-1", "display_name": "Reference One"}]
    rid = mgr.start("t1", "v1", "Use the reference.", {}, mentions, runner=runner)

    assert _wait_status(mgr, rid) == "succeeded"
    assert received["effect_mentions"] == mentions
    tmp.cleanup()


def test_start_passes_selected_option_id_to_supported_runner():
    """A structured option selection reaches the agent without text re-interpretation."""
    mgr, tmp = _make_mgr()
    received = {}

    def runner(
        run_id,
        thread_id,
        video_id,
        user_input,
        pinned_joints,
        selected_option_id,
        cancel_event,
        resume_checkpoint_id,
        on_event,
        on_tool_event,
    ):
        received["selected_option_id"] = selected_option_id
        return {"response": "ok", "checkpoint_id": "cp-option"}

    rid = mgr.start(
        "t1",
        "v1",
        "Orbiting rings",
        {},
        selected_option_id="option-123",
        runner=runner,
    )

    assert _wait_status(mgr, rid) == "succeeded"
    assert received["selected_option_id"] == "option-123"
    tmp.cleanup()


def test_start_passes_the_fixed_editor_context_to_a_supported_runner():
    """The runner receives the context captured before its worker starts."""
    mgr, tmp = _make_mgr()
    received = {}
    context = EditorContextSnapshot(
        effect_id="workspace-1",
        video_id="video-1",
        editor_revision=3,
        editor_state=empty_editor_state("video-1", 230),
        selection=EditorSelection(current_frame=42),
    )

    def runner(
        run_id,
        thread_id,
        video_id,
        user_input,
        pinned_joints,
        editor_context,
        cancel_event,
        resume_checkpoint_id,
        on_event,
        on_tool_event,
    ):
        received["editor_context"] = editor_context
        return {"response": "ok", "checkpoint_id": "cp-editor"}

    rid = mgr.start(
        "workspace-1",
        "video-1",
        "Draw at p1.",
        {},
        editor_context=context,
        runner=runner,
    )

    assert _wait_status(mgr, rid) == "succeeded"
    assert received["editor_context"] is context
    tmp.cleanup()
