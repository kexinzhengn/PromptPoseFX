"""ChatManager 单元测试：存储、读取、列表、覆盖、不存在"""

import json
import tempfile
from chat_manager import ChatManager


def _make_cm():
    """创建使用临时目录的 ChatManager"""
    tmpdir = tempfile.TemporaryDirectory()
    cm = ChatManager(data_dir=tmpdir.name)
    return cm, tmpdir


# ====== save + get ======

def test_save_and_get():
    cm, tmp = _make_cm()
    cm.save_effect("e1", "code_a", {"size": 10}, "效果A")
    detail = cm.get_effect_detail("e1")
    assert detail is not None
    assert detail["name"] == "效果A"
    assert detail["code"] == "code_a"
    assert detail["params"] == {"size": 10}
    assert detail["effect_id"] == "e1"
    tmp.cleanup()


def test_get_nonexistent():
    cm, tmp = _make_cm()
    assert cm.get_effect_detail("不存在") is None
    tmp.cleanup()


# ====== 效果列表 ======

def test_empty_list():
    cm, tmp = _make_cm()
    assert cm.get_effect_list() == []
    tmp.cleanup()


def test_list_after_save():
    cm, tmp = _make_cm()
    cm.save_effect("e1", "c1", {}, "效果A")
    cm.save_effect("e2", "c2", {}, "效果B")
    lst = cm.get_effect_list()
    assert len(lst) == 2
    names = {e["name"] for e in lst}
    assert names == {"效果A", "效果B"}
    tmp.cleanup()


# ====== 覆盖更新 ======

def test_overwrite():
    cm, tmp = _make_cm()
    cm.save_effect("e1", "old_code", {"v": 1}, "旧名")
    cm.save_effect("e1", "new_code", {"v": 2}, "新名")
    detail = cm.get_effect_detail("e1")
    assert detail["code"] == "new_code"
    assert detail["params"]["v"] == 2
    assert detail["name"] == "新名"
    # 列表仍然只有 1 个
    assert len(cm.get_effect_list()) == 1
    tmp.cleanup()


# ====== 多次保存 ======

def test_multiple_effects_independent():
    cm, tmp = _make_cm()
    cm.save_effect("a", "code_a", {"x": 1}, "A")
    cm.save_effect("b", "code_b", {"y": 2}, "B")

    a = cm.get_effect_detail("a")
    b = cm.get_effect_detail("b")
    assert a["code"] == "code_a"
    assert b["code"] == "code_b"

    lst = cm.get_effect_list()
    assert len(lst) == 2
    tmp.cleanup()


# ====== 文件实际写入 ======

def test_file_persistence():
    """验证数据确实写入了文件（而不是只存在内存）"""
    tmpdir = tempfile.TemporaryDirectory()
    cm = ChatManager(data_dir=tmpdir.name)
    cm.save_effect("p1", "persist", {"k": "v"}, "持久化测试")
    cm2 = ChatManager(data_dir=tmpdir.name)  # 重新加载
    detail = cm2.get_effect_detail("p1")
    assert detail is not None
    assert detail["code"] == "persist"
    assert detail["params"]["k"] == "v"
    tmpdir.cleanup()


# ====== 空代码/空参数 ======

def test_empty_code_and_params():
    cm, tmp = _make_cm()
    cm.save_effect("empty", "", {}, "空效果")
    detail = cm.get_effect_detail("empty")
    assert detail["code"] == ""
    assert detail["params"] == {}
    tmp.cleanup()


# ====== 草稿状态 ======

def test_draft_status():
    """草稿保存为 draft，默认保存为 active，列表与详情都带状态"""
    cm, tmp = _make_cm()
    cm.save_effect("d1", "draft_code", {}, "草稿效果", status="draft")
    cm.save_effect("a1", "active_code", {}, "正式效果")

    assert cm.get_effect_detail("d1")["status"] == "draft"
    assert cm.get_effect_detail("a1")["status"] == "active"

    lst = cm.get_effect_list()
    by_id = {e["id"]: e["status"] for e in lst}
    assert by_id == {"d1": "draft", "a1": "active"}
    tmp.cleanup()


# ====== 多实例一致性 ======

def test_cross_instance_visibility():
    """一个 ChatManager 写入的效果，另一个实例（如 API 层）应立即读到"""
    tmpdir = tempfile.TemporaryDirectory()
    # 先创建 reader（模拟 API 层早已启动、内存索引为空）
    reader = ChatManager(data_dir=tmpdir.name)
    writer = ChatManager(data_dir=tmpdir.name)
    writer.save_effect("x1", "code_x", {"v": 1}, "跨实例效果")

    lst = reader.get_effect_list()
    assert len(lst) == 1
    assert lst[0]["id"] == "x1"
    assert reader.get_effect_detail("x1")["name"] == "跨实例效果"
    tmpdir.cleanup()


def test_get_conversation_without_effect_files():
    """只有对话、没有效果文件（失败的新线程）也能读到对话记录"""
    tmpdir = tempfile.TemporaryDirectory()
    cm = ChatManager(data_dir=tmpdir.name)
    cm.save_conversation("thread-failed", [
        {"role": "user", "content": "做一个效果"},
        {"role": "assistant", "content": "出错了", "isError": True},
    ])

    # 没有 code.js/params.json，get_effect_detail 应为 None
    assert cm.get_effect_detail("thread-failed") is None
    # 但对话记录可读
    conv = cm.get_conversation("thread-failed")
    assert conv[-1]["role"] == "assistant"
    assert conv[-1]["isError"] is True

    # 不存在的线程返回空列表
    assert cm.get_conversation("不存在的线程") == []
    tmpdir.cleanup()


def test_delete_effect():
    """删除效果后目录与索引都不再存在"""
    cm, tmp = _make_cm()
    cm.save_effect("del1", "code", {"x": 1}, "待删除")
    assert cm.delete_effect("del1") is True
    assert cm.get_effect_detail("del1") is None
    assert cm.get_effect_list() == []
    assert cm.delete_effect("不存在的效果") is False
    tmp.cleanup()
