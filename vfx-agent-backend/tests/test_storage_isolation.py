"""Safety tests for per-test chat storage isolation."""

from pathlib import Path

from chat_manager import ChatManager


def test_default_chat_manager_uses_per_test_storage(
    isolated_chat_storage: Path,
) -> None:
    """Default storage must stay inside the current test's temporary directory."""
    manager = ChatManager()
    manager.save_effect("isolated-effect", "class Effect {}", {}, "Isolated Effect")

    assert Path(manager.data_dir) == isolated_chat_storage
    assert manager.get_effect_detail("isolated-effect") is not None
