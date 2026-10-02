import json
import os
from typing import Any

from agent.control_bindings import extract_control_bindings
from editor_controls import EditorContextSnapshot, EditorSelection, EditorState
from effect_repository import EffectRepository, EffectSnapshot


class ChatManager:
    """Persist Effect code, metadata, controls, and conversation history."""

    def __init__(self, data_dir: str = None):
        from config import CHAT_DATA_DIR
        self.data_dir = data_dir or CHAT_DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        self.effects = EffectRepository(self.data_dir)

    # Workspace operations.

    def create_workspace(
        self,
        effect_id: str,
        video_id: str,
        total_frames: int,
    ) -> dict:
        """Create or return a pending Effect Workspace for one video."""
        snapshot = self.effects.create_workspace(effect_id, video_id, total_frames)
        return self._snapshot_to_detail(snapshot)

    def replace_editor_state(
        self,
        effect_id: str,
        expected_revision: int,
        editor_state: EditorState | dict[str, Any],
    ) -> dict:
        """Replace editor-owned controls using optimistic concurrency."""
        snapshot = self.effects.replace_editor_state(
            effect_id,
            expected_revision,
            editor_state,
        )
        return self._snapshot_to_detail(snapshot)

    def get_editor_context_snapshot(
        self,
        effect_id: str,
        video_id: str,
        expected_revision: int,
        selection: EditorSelection | dict[str, Any],
    ) -> EditorContextSnapshot:
        """Return editor-owned controls fixed at one validated revision."""
        return self.effects.get_editor_context_snapshot(
            effect_id,
            video_id,
            expected_revision,
            selection,
        )

    # Conversation history.

    def save_conversation(self, effect_id: str, messages: list[dict]):
        """Persist conversation history for one Effect workspace."""
        effect_dir = os.path.join(self.data_dir, effect_id)
        os.makedirs(effect_dir, exist_ok=True)
        path = os.path.join(effect_dir, "conversation.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    def load_conversation(self, effect_id: str) -> list[dict]:
        """Load conversation history for one Effect workspace."""
        path = os.path.join(self.data_dir, effect_id, "conversation.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_conversation(self, thread_id: str) -> list[dict]:
        """Load thread history even when no generated Effect exists."""
        return self.load_conversation(thread_id)

    # Effect operations.

    def save_effect(
        self,
        effect_id: str,
        code: str,
        params: dict,
        effect_name: str,
        status: str = "active",
    ) -> dict:
        """Store or replace one Effect snapshot.

        Args:
            status: ``active`` for submitted effects or ``draft`` for failed output.
        """
        snapshot = self.effects.save_effect(
            effect_id,
            code,
            params,
            effect_name,
            status,
        )
        return self._snapshot_to_detail(snapshot)

    def save_generated_effect(
        self,
        effect_id: str,
        code: str,
        effect_name: str,
        base_name: str = "",
        explicit_parameter_updates: dict[str, Any] | None = None,
        status: str = "active",
        generation_metadata: dict[str, Any] | None = None,
        editor_context: EditorContextSnapshot | None = None,
    ) -> dict:
        """Save generated code without overwriting newer user metadata or parameters."""
        snapshot = self.effects.save_generated_effect(
            effect_id=effect_id,
            code=code,
            requested_name=effect_name,
            base_name=base_name,
            explicit_parameter_updates=explicit_parameter_updates,
            status=status,
            generation_metadata=generation_metadata,
            editor_context=editor_context,
        )
        return self._snapshot_to_detail(snapshot)

    def patch_effect(
        self,
        effect_id: str,
        effect_name: str | None = None,
        parameter_updates: dict[str, Any] | None = None,
        parameter_range_updates: dict[str, dict[str, float]] | None = None,
    ) -> dict:
        """Patch an Effect name or current parameters without changing its code."""
        snapshot = self.effects.patch_effect(
            effect_id,
            requested_name=effect_name,
            parameter_updates=parameter_updates,
            parameter_range_updates=parameter_range_updates,
        )
        return self._snapshot_to_detail(snapshot)

    def save_draft_effect(
        self,
        effect_id: str,
        code: str,
        effect_name: str,
        base_name: str = "",
        generation_metadata: dict[str, Any] | None = None,
        editor_context: EditorContextSnapshot | None = None,
    ) -> dict:
        """Save a failed generation draft without overwriting newer user metadata."""
        snapshot = self.effects.save_draft_effect(
            effect_id=effect_id,
            code=code,
            requested_name=effect_name,
            base_name=base_name,
            generation_metadata=generation_metadata,
            editor_context=editor_context,
        )
        return self._snapshot_to_detail(snapshot)

    def delete_effect(self, effect_id: str) -> bool:
        """Delete an Effect directory and remove it from the index."""
        return self.effects.delete(effect_id)

    def get_effect_detail(self, effect_id: str) -> dict | None:
        """Return a complete Effect snapshot, or ``None`` when missing."""
        snapshot = self.effects.get(effect_id)
        if snapshot is None:
            return None
        detail = self._snapshot_to_detail(snapshot)
        detail["conversation"] = self.load_conversation(effect_id)
        return detail

    def get_effect_list(self) -> list[dict]:
        """Return all Effect summaries."""
        return [
            {
                "id": snapshot.effect_id,
                "name": snapshot.name,
                "status": snapshot.status,
                "updated_at": snapshot.updated_at,
                "revision": snapshot.revision,
            }
            for snapshot in self.effects.list()
        ]

    @staticmethod
    def _snapshot_to_detail(snapshot: EffectSnapshot) -> dict:
        bindings, binding_errors = extract_control_bindings(snapshot.code)
        bound_control_ids = [] if binding_errors else sorted({
            binding["id"] for binding in bindings.values()
        })
        return {
            "effect_id": snapshot.effect_id,
            "name": snapshot.name,
            "status": snapshot.status,
            "code": snapshot.code,
            "params": snapshot.params,
            "parameter_ranges": snapshot.parameter_ranges,
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
            "revision": snapshot.revision,
            "generation_metadata": snapshot.generation_metadata,
            "video_id": snapshot.video_id,
            "total_frames": snapshot.total_frames,
            "editor_revision": snapshot.editor_revision,
            "bound_control_ids": bound_control_ids,
            "editor_state": (
                snapshot.editor_state.model_dump(mode="json")
                if snapshot.editor_state is not None
                else None
            ),
        }
