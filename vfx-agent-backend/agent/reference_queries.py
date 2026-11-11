"""Track independently resolved sources and validate their use in generation."""

from collections import Counter
import uuid


def reference_queries_with_results(previous, queries, results):
    pending = {item["id"]: item for item in previous}
    for query, result in zip(queries, results, strict=True):
        query_id = query["replace_query_id"] or uuid.uuid4().hex
        candidates = result["candidates"]
        status = result["status"]
        pending[query_id] = {
            "id": query_id,
            "source_description": query["source_description"],
            "original_expression": query["original_expression"],
            "reference_intent": query["reference_intent"],
            "status": status,
            "candidates": candidates,
            "effect_id": candidates[0]["effect_id"] if status == "matched" else "",
        }
    return list(pending.values())


def reference_interruption(queries):
    """Use the existing clarification response for backend-generated choices."""
    for query in queries:
        status = query["status"]
        if status == "matched":
            continue
        source = query["source_description"]
        if status != "ambiguous":
            if status == "unavailable":
                message = f'I could not verify all matches for "{source}". Name or @mention the Effect to continue.'
            else:
                message = f'I could not find "{source}". Name or @mention an active Effect to continue.'
            return {
                "main_action": {"action": "respond", "message": message},
                "action_name": "respond",
            }
        options = {}
        visible_options = []
        for candidate in query["candidates"]:
            option_id = uuid.uuid4().hex
            effect_id = candidate["effect_id"]
            options[option_id] = {"reference_query_id": query["id"], "effect_id": effect_id}
            visible_options.append({
                "id": option_id,
                "label": candidate["name"],
                "description": candidate.get("summary") or query["reference_intent"],
            })
        return {
            "action_name": "clarify",
            "pending_options": options,
            "action_result": {
                "question": f'Which Effect did you mean by "{source}"?',
                "options": visible_options,
            },
        }
    return {}


def validate_generation_references(queries, references, mentioned_ids):
    if any(query["status"] != "matched" for query in queries):
        return "Resolve each pending reference before generating."
    required = Counter((query["effect_id"], query["reference_intent"]) for query in queries)
    supplied = Counter((reference["effect_id"], reference["reference_intent"]) for reference in references)
    if required - supplied:
        return "Include every confirmed Effect ID and its original reuse intent verbatim in references."
    if any(effect_id not in mentioned_ids for effect_id, _ in supplied - required):
        return "Only reuse additional aspects from a trusted @mention or a new resolved query."
    return None


def restore_reference_queries(queries, active_ids, option):
    """Recheck stored IDs before reusing bindings or presenting options."""
    restored = []
    for query in queries:
        candidates = [
            candidate for candidate in query["candidates"]
            if candidate["effect_id"] in active_ids
        ]
        item = {**query, "candidates": candidates}
        if option.get("reference_query_id") == query["id"] and query["status"] == "ambiguous":
            chosen = option["effect_id"]
            if any(candidate["effect_id"] == chosen for candidate in candidates):
                item.update(status="matched", effect_id=chosen)
            else:
                item.update(status="not_found", effect_id="")
        elif query["status"] == "matched" and query["effect_id"] not in active_ids:
            item.update(status="not_found", effect_id="")
        elif query["status"] == "ambiguous" and not candidates:
            item.update(status="not_found", effect_id="")
        restored.append(item)
    return restored
