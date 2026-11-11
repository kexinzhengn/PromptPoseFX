"""Retrieval and snapshot evidence regression coverage."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from agent.effect_analyzer import EffectAnalyzer, ReferenceAnalysisError, source_from_detail
from agent.reference_resolver import ReferenceResolver
from agent.schemas import ReferenceSafeSummary
from chat_manager import ChatManager
from tests.test_agent import _FAKE_CODE



RIPPLE_CODE = """class Effect {
      static CONTRACT_VERSION = 2;
      static CONFIG = {
        speed: {type: 'range', default: 1, min: 0.1, max: 3, step: 0.1,
          label: 'Speed', description: 'Expansion speed'},
        tint: {type: 'color', default: '#3399FF', label: 'Tint', description: 'Ring color'}
      };
      constructor() {}
      display(sketch, frameData, params) {
        const wrist = frameData.joints.left_wrist;
        const phase = (frameData.currentFrame * params.speed) % 90;
        sketch.push();
        sketch.noFill();
        sketch.stroke(params.tint);
        for (let i = 0; i < 3; i++) {
          const radius = (phase + i * 30) % 90;
          sketch.circle(wrist.x, wrist.y, radius * 2);
        }
        sketch.pop();
      }
    }"""

def query(description="water ripples", intent="Reuse its spreading motion"):
    return {
        "source_description": description,
        "original_expression": description,
        "reference_intent": intent,
    }


def summary_analyzer():
    analyzer = Mock()
    analyzer.summarize.side_effect = lambda source: ReferenceSafeSummary(
        effect_id=source.effect_id, summary="Concentric ripples spread outward."
    )
    return analyzer


def selection_call(**kwargs):
    data = json.loads(kwargs["user"])
    return kwargs["output_schema"](effect_ids=[
        item["effect_id"] for item in data["candidates"]
    ])


def test_summaries_are_cached_invalidated_and_deleted(isolated_chat_storage):
    manager = ChatManager(str(isolated_chat_storage))
    manager.save_effect("ripples", _FAKE_CODE, {"size": 24}, "Ripples", status="active")
    analyzer = summary_analyzer()
    resolver = ReferenceResolver(manager, analyzer, selection_call)
    result = resolver.resolve([query()], "new")
    assert result["results"][0]["status"] == "matched"
    assert analyzer.summarize.call_count == 1
    resolver.resolve([query()], "new")
    assert analyzer.summarize.call_count == 1
    manager.save_effect("ripples", _FAKE_CODE, {"size": 30}, "Ripples", status="active")
    resolver.resolve([query()], "new")
    assert analyzer.summarize.call_count == 2
    assert analyzer.summarize.call_args.args[0].params["size"] == 30
    cache_files = list(isolated_chat_storage.rglob("reference_summary.json"))
    assert len(cache_files) == 1
    manager.delete_effect("ripples")
    assert not cache_files[0].exists()
    assert resolver.resolve([query()], "new")["results"][0]["status"] == "not_found"


def test_batches_preserve_ambiguity_and_exclude_current_and_drafts(isolated_chat_storage):
    manager = ChatManager(str(isolated_chat_storage))
    for index in range(22):
        manager.save_effect(str(index), _FAKE_CODE, {}, f"Ripple {index}", status="active")
    manager.save_effect("draft", _FAKE_CODE, {}, "Draft", status="draft")
    calls = []

    def select(**kwargs):
        calls.append(json.loads(kwargs["user"]))
        return selection_call(**kwargs)

    result = ReferenceResolver(manager, summary_analyzer(), select).resolve([query()], "0")
    assert [len(call["candidates"]) for call in calls] == [20, 1]
    assert result["results"][0]["status"] == "ambiguous"
    assert len(result["results"][0]["candidates"]) == 21


def test_failed_summary_keeps_name_lookup_and_reports_incomplete(isolated_chat_storage):
    manager = ChatManager(str(isolated_chat_storage))
    manager.save_effect("halo", _FAKE_CODE, {}, "Halo", status="active")
    analyzer = Mock()
    analyzer.summarize.side_effect = ReferenceAnalysisError("unavailable")
    select = Mock()
    resolver = ReferenceResolver(manager, analyzer, select)
    result = resolver.resolve([query("Halo"), {**query(), "most_recent": True}], "new")
    assert [item["status"] for item in result["results"]] == ["matched", "matched"]
    analyzer.summarize.assert_not_called()
    select.assert_not_called()
    select.side_effect = RuntimeError("matching service unavailable")
    result = resolver.resolve([query(), query("Halo")], "new")
    assert result["incomplete_summary_ids"] == ["halo"]
    assert [item["status"] for item in result["results"]] == ["unavailable", "matched"]


def test_latest_timestamp_tie_remains_ambiguous():
    manager = Mock()
    manager.get_effect_list.return_value = [
        {"id": key, "name": key, "status": "active", "updated_at": "same"} for key in ("a", "b")
    ]
    manager.get_effect_detail.side_effect = lambda key: {
        "effect_id": key, "code": _FAKE_CODE, "status": "active",
        "name": key, "revision": 1, "updated_at": "same",
    }
    manager.effects.get_reference_summary.return_value = "A flowing shape."
    result = ReferenceResolver(manager).resolve([{**query(), "most_recent": True}], "new")
    assert result["results"][0]["status"] == "ambiguous"


def test_deleted_source_is_not_recreated_by_inflight_summary(isolated_chat_storage):
    manager = ChatManager(str(isolated_chat_storage))
    manager.save_effect("a", _FAKE_CODE, {}, "A", status="active")
    detail = manager.get_effect_detail("a")
    manager.delete_effect("a")
    manager.effects.cache_reference_summary(
        "a", {"revision": detail["revision"], "editor_revision": 0, "format": 1},
        "A flowing shape.",
    )
    assert manager.get_effect_detail("a") is None
    assert not list(isolated_chat_storage.rglob("reference_summary.json"))


@pytest.mark.parametrize("path,value", [
    (["params", "size"], 42),
    (["editor_state", "paths", "0", "points", "0", "x"], 0.25),
])
def test_state_evidence_is_verified_against_actual_snapshot(path, value):
    detail = {
        "effect_id": "a", "code": _FAKE_CODE, "params": {"size": 42},
        "editor_state": {"paths": [{"points": [{"x": 0.25}]}]},
        "revision": 7, "editor_revision": 3, "video_id": "video", "total_frames": 180,
    }

    def call(**kwargs):
        state = json.loads(kwargs["user"].split("SOURCE STATE:\n")[1].split("\nSOURCE CODE:")[0])
        assert state["params"]["size"] == 42
        return kwargs["output_schema"](findings=[{
            "source": "state", "path": path, "evidence": json.dumps(value),
            "role": "requested behavior", "usage": "Adapt this value to the target.",
        }])

    evidence = EffectAnalyzer(structured_call=call).analyze_evidence([
        source_from_detail(detail, "Reuse its spatial arrangement.")
    ])[0]
    assert evidence.revision == 7
    assert evidence.editor_revision == 3
    assert evidence.video_id == "video"
    assert json.loads(evidence.findings[0].evidence) == value


def test_fabricated_state_value_is_rejected():
    def call(**kwargs):
        return kwargs["output_schema"](findings=[{
            "source": "state", "path": ["params", "size"], "evidence": "99",
            "role": "size", "usage": "Reuse this size.",
        }])
    source = source_from_detail({
        "effect_id": "a", "code": _FAKE_CODE, "params": {"size": 42}
    }, "Reuse size")
    with pytest.raises(ReferenceAnalysisError, match="snapshot"):
        EffectAnalyzer(structured_call=call).analyze_evidence([source])


@pytest.mark.live
def test_real_model_resolves_multilingual_descriptions_and_verifies_evidence(isolated_chat_storage):
    import config

    if not config.API_KEY:
        pytest.skip("An LLM API key is required")
    manager = ChatManager(str(isolated_chat_storage))
    manager.save_effect("ripples", RIPPLE_CODE, {"speed": 2, "tint": "#AA33FF"}, "Aurora", status="active")
    manager.save_effect("dot", _FAKE_CODE, {"size": 24}, "Beacon", status="active")
    resolver = ReferenceResolver(manager)
    requests = [
        query("之前那个像水波一样散开的效果", "沿用向外扩散的运动方式"),
        query("the earlier expanding concentric rings", "Reuse its pacing"),
    ]
    result = resolver.resolve(requests, "new")
    assert not result["incomplete_summary_ids"]
    assert all(item["status"] == "matched" for item in result["results"])
    assert all(item["candidates"][0]["effect_id"] == "ripples" for item in result["results"])
    evidence = EffectAnalyzer().analyze_evidence([
        source_from_detail(manager.get_effect_detail("ripples"), "Reuse expansion speed and saved palette")
    ])[0]
    assert any(item.source == "state" for item in evidence.findings)
    assert evidence.revision == manager.get_effect_detail("ripples")["revision"]
    from agent.agent import _agent_node, _build_trusted_context
    from agent.prompts import MAIN_AGENT_SYSTEM
    from langchain_core.messages import SystemMessage, HumanMessage

    context = _build_trusted_context("create", None, manager.get_effect_list(), {}, [])
    for phrase in [
        "用之前那个像水波一样散开的效果的运动方式，做一个右手腕特效",
        "Use the expanding ripple effect's motion for a new right wrist effect",
    ]:
        response = _agent_node({
            "messages": [SystemMessage(content=MAIN_AGENT_SYSTEM),
                         SystemMessage(content=context), HumanMessage(content=phrase)],
            "operation": "create", "user_input": phrase,
        })
        assert response["action_name"] == "resolve_references"
        assert response["main_action"]["queries"][0]["reference_intent"]
    print(json.dumps({"metrics": result["metrics"], "evidence": evidence.model_dump()}, ensure_ascii=False))


def test_ambiguous_candidate_selection_keeps_multiple_sources_and_saved_state(
    isolated_chat_storage, monkeypatch,
):
    from langchain_core.messages import AIMessage
    from agent import agent as main
    from agent.schemas import CodeAgentResult, ReferenceEvidence

    manager = main._chat_manager
    for effect_id in ("ripple-a", "ripple-b", "ribbon"):
        manager.save_effect(effect_id, _FAKE_CODE, {"size": 42}, effect_id, status="active")

    def action(name, args):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])

    model = Mock()
    model.bind_tools.return_value = model
    references = [
        {"effect_id": "ripple-b", "reference_intent": "Use its movement"},
        {"effect_id": "ribbon", "reference_intent": "Use its style"},
    ]
    model.invoke.side_effect = [
        action("resolve_references", {"queries": [
            query("ribbon", "Use its style"),
            query(intent="Use its movement"),
            query("one with a slow pulse", "Use its pacing"),
        ]}),
        action("generate_effect", {
            "user_description": "Create a wrist trail using both the movement and style.",
            "requested_name": "Ripple Ribbon",
            "references": references,
        }),
        action("generate_effect", {
            "user_description": "Create a wrist trail using all three references.",
            "requested_name": "Ripple Ribbon",
            "references": references + [{"effect_id": "ripple-a", "reference_intent": "Use its pacing"}],
        }),
    ]
    monkeypatch.setattr("agent.llm.get_main_agent_llm", lambda: model)
    resolver = Mock()
    resolver.resolve.return_value = {"results": [
        {"status": "matched", "candidates": [{"effect_id": "ribbon", "name": "ribbon"}]},
        {"status": "ambiguous", "candidates": [
            {"effect_id": "ribbon", "name": "ribbon"}, {"effect_id": "ripple-b", "name": "ripple-b"},
        ]},
        {"status": "ambiguous", "candidates": [
            {"effect_id": "ripple-a", "name": "ripple-a"}, {"effect_id": "ripple-b", "name": "ripple-b"},
        ]},
    ]}
    monkeypatch.setattr(main, "ReferenceResolver", lambda manager: resolver)
    captured = []

    def analyze(sources):
        captured.extend(sources)
        return [ReferenceEvidence(
            effect_id=source.effect_id, reference_intent=source.reference_intent,
            revision=source.revision, findings=[{
                "source": "state", "path": ["params", "size"], "evidence": "42",
                "role": "size", "usage": "Use saved size.",
            }],
        ) for source in sources]

    analyzer = Mock()
    analyzer.analyze_evidence.side_effect = analyze
    monkeypatch.setattr(main, "EffectAnalyzer", lambda: analyzer)
    code_agent = Mock(return_value=CodeAgentResult(status="submitted", code=_FAKE_CODE))
    monkeypatch.setattr("agent.tools.code_agent_module.invoke_code_agent", code_agent)

    args = {
        "video_id": "video", "thread_id": "new", "effect_id": "new",
        "effect_messages": [], "prev_code": "", "effect_name": "", "effect_list": [],
    }
    first = main.process_user_message(user_input="Use the earlier ripples and ribbon style", **args)
    assert [option["label"] for option in first["options"]] == ["ribbon", "ripple-b"]
    second = main.process_user_message(
        user_input="ripple-b", selected_option_id=first["options"][1]["id"], **args,
    )
    assert [option["label"] for option in second["options"]] == ["ripple-a", "ripple-b"]
    code_agent.assert_not_called()
    third = main.process_user_message(
        user_input="ripple-a", selected_option_id=second["options"][0]["id"], **args,
    )
    assert third["new_effect"]
    assert [source.effect_id for source in captured] == ["ripple-b", "ribbon", "ripple-a"]
    assert all(source.params["size"] == 42 for source in captured)
    assert model.invoke.call_count == 3
    saved = manager.get_effect_detail("new")["generation_metadata"]
    assert len(saved["reference_evidence"]) == 3
    assert code_agent.call_args.kwargs["reference_evidence"] == saved["reference_evidence"]


def test_editor_revision_invalidates_summary(isolated_chat_storage):
    from editor_controls import empty_editor_state

    manager = ChatManager(str(isolated_chat_storage))
    manager.create_workspace("a", "video", 180)
    manager.save_effect("a", _FAKE_CODE, {}, "A", status="active")
    analyzer = summary_analyzer()
    resolver = ReferenceResolver(manager, analyzer, selection_call)
    resolver.resolve([query()], "new")
    state = empty_editor_state("video", 180).model_dump(mode="json")
    state["active_interval"]["end_frame"] = 150
    manager.replace_editor_state("a", 0, state)
    resolver.resolve([query()], "new")
    assert analyzer.summarize.call_count == 2
    assert analyzer.summarize.call_args.args[0].editor_state["active_interval"]["end_frame"] == 150


@pytest.mark.live
def test_real_reference_generation_runs_through_normal_entrypoint(tmp_path):
    import config
    from agent import agent as main
    from agent.hard_validate import hard_validate_effect

    if not config.API_KEY:
        pytest.skip("An LLM API key is required")
    main._chat_manager.save_effect(
        "ripples", RIPPLE_CODE, {"speed": 2, "tint": "#AA33FF"}, "Aurora", status="active"
    )
    result = main.process_user_message(
        user_input="沿用之前那个像水波一样向外散开的特效的扩散运动和配色，在右手腕生成三圈向外扩散的圆环。",
        video_id="001", thread_id="new-ripples", effect_id="new-ripples",
        effect_messages=[], prev_code="", effect_name="", effect_list=[],
    )
    assert result["new_effect"], result
    detail = main._chat_manager.get_effect_detail("new-ripples")
    assert detail["generation_metadata"]["references"][0]["effect_id"] == "ripples"
    assert detail["generation_metadata"]["reference_evidence"]
    validation = hard_validate_effect(
        detail["code"], Path(config.POSE_DATA_DIR) / "001" / "smoothed_landmark.json"
    )
    assert validation.passed, validation.errors
    code_path = tmp_path / "generated-reference.js"
    code_path.write_text(detail["code"], encoding="utf-8")
    (tmp_path / "params.json").write_text(json.dumps(detail["params"]), encoding="utf-8")
    print("Generated reference preview source:", code_path)


@pytest.mark.parametrize("scenario", ["rename", "delete", "save_retry"])
def test_follow_up_keeps_bound_source_until_successful_save(monkeypatch, scenario):
    from agent import agent as main
    from agent.schemas import CodeAgentResult, ReferenceEvidence
    from langchain_core.messages import AIMessage

    manager = main._chat_manager
    manager.save_effect("original", _FAKE_CODE, {"size": 42}, "Halo", status="active")

    def tool_call(name, args):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])

    generation = tool_call("generate_effect", {
        "requested_name": "Wrist pulse",
        "user_description": "Make a pulse around the right wrist using the referenced size.",
        "references": [{"effect_id": "original", "reference_intent": "Use its size"}],
    })
    model = Mock()
    model.bind_tools.return_value = model
    model.invoke.side_effect = [
        tool_call("resolve_references", {"queries": [query("Halo", "Use its size")]}),
        AIMessage(content="What Effect would you like to create?"),
        generation,
        generation.model_copy(),
    ]
    monkeypatch.setattr("agent.llm.get_main_agent_llm", lambda: model)
    analyzer = Mock()
    analyzer.analyze_evidence.return_value = [ReferenceEvidence(
        effect_id="original", reference_intent="Use its size",
        findings=[{"role": "size", "evidence": "42", "usage": "Use the saved size."}],
    )]
    monkeypatch.setattr(main, "EffectAnalyzer", lambda: analyzer)
    code_agent = Mock(return_value=CodeAgentResult(status="submitted", code=_FAKE_CODE))
    monkeypatch.setattr("agent.tools.code_agent_module.invoke_code_agent", code_agent)
    args = {
        "video_id": "001", "thread_id": "new", "effect_id": "new",
        "effect_messages": [], "prev_code": "", "effect_name": "", "effect_list": [],
    }
    first = main.process_user_message(user_input="Use the Halo Effect's size.", **args)
    assert first["response"] == "What Effect would you like to create?"
    code_agent.assert_not_called()

    if scenario == "delete":
        manager.delete_effect("original")
    else:
        manager.patch_effect("original", effect_name="Renamed")
    manager.save_effect("new-halo", _FAKE_CODE, {"size": 18}, "Halo", status="active")

    save = manager.save_generated_effect
    if scenario == "save_retry":
        save_mock = Mock(side_effect=main.EffectEditorStateError("The control changed during generation."))
        monkeypatch.setattr(manager, "save_generated_effect", save_mock)

    second = main.process_user_message(user_input="A pulse around the right wrist.", **args)
    if scenario == "save_retry":
        assert not second["new_effect"]
        assert "not saved" in second["response"]
        save_mock.assert_called_once()
        monkeypatch.setattr(manager, "save_generated_effect", save)
        second = main.process_user_message(
            user_input="Try again.", resume_checkpoint_id=second["checkpoint_id"], **args,
        )
        assert code_agent.call_count == 2
    if scenario == "delete":
        assert "Name or @mention an active Effect" in second["response"]
        assert not second["new_effect"]
        analyzer.analyze_evidence.assert_not_called()
        code_agent.assert_not_called()
    else:
        assert second["new_effect"]
        source = analyzer.analyze_evidence.call_args.args[0][0]
        assert source.effect_id == "original"
        assert source.params["size"] == 42
        assert code_agent.call_count == (2 if scenario == "save_retry" else 1)
        completed = main._get_main_graph().get_state({"configurable": {
            "thread_id": main._checkpoint_thread_id("new"), "checkpoint_id": second["checkpoint_id"],
        }})
        assert completed.values["reference_queries"] == []


@pytest.mark.live
def test_real_model_continues_multi_source_reference_after_rename():
    import config
    from agent import agent as main

    if not config.API_KEY:
        pytest.skip("An LLM API key is required")
    manager = main._chat_manager
    manager.save_effect("motion", RIPPLE_CODE, {"speed": 2}, "Aurora", status="active")
    manager.save_effect("palette", RIPPLE_CODE, {"tint": "#AA33FF"}, "Beacon", status="active")
    args = {
        "video_id": "001", "thread_id": "new", "effect_id": "new",
        "effect_messages": [], "prev_code": "", "effect_name": "", "effect_list": [],
    }
    first = main.process_user_message(
        user_input="I want to reuse Aurora's expansion motion and Beacon's saved ring color. "
        "Ask what I want to make before generating.", **args,
    )
    assert not first["new_effect"], first
    assert first["response"]
    checkpoint = main._get_main_graph().get_state({
        "configurable": {"thread_id": main._checkpoint_thread_id("new")},
    })
    queries = checkpoint.values["reference_queries"]
    assert {item["effect_id"] for item in queries} == {"motion", "palette"}
    manager.patch_effect("motion", effect_name="Renamed Aurora")
    manager.save_effect("new-aurora", RIPPLE_CODE, {"speed": 1}, "Aurora", status="active")
    second = main.process_user_message(
        user_input="Make three expanding concentric rings centered on the right wrist.", **args,
    )
    assert second["new_effect"], second
    metadata = manager.get_effect_detail("new")["generation_metadata"]
    assert {item["effect_id"] for item in metadata["references"]} == {"motion", "palette"}
    assert {item["effect_id"] for item in metadata["reference_evidence"]} == {"motion", "palette"}
