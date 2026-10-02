import json
from typing import Any

from .config_contract import validate_static_config


def extract_config(code: str) -> tuple[bool, str]:
    """Extract defaults from a CONFIG that satisfies the shared contract."""
    config, errors = validate_static_config(code)
    if errors:
        return False, "; ".join(errors)

    params = {
        param_name: metadata["default"]
        for param_name, metadata in config.items()
    }
    return True, json.dumps(params, ensure_ascii=False)


def extract_config_labels_and_descriptions(code: str) -> list[dict[str, Any]]:
    """Return validated CONFIG labels and descriptions for product messages."""
    config, errors = validate_static_config(code)
    if errors:
        return []

    return [
        {
            "key": param_name,
            "label": metadata["label"],
            "description": metadata["description"],
        }
        for param_name, metadata in config.items()
    ]
