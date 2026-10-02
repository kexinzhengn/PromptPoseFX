"""Static Effect control-binding extraction without executing generated code."""

from __future__ import annotations

from .config_contract import parse_static_object_literal


SUPPORTED_CONTROL_BINDING_TYPES = {"path", "point", "time_marker"}


def extract_control_bindings(code: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return validated binding names mapped to control type and Stable ID."""
    raw_bindings, errors = parse_static_object_literal(code, "CONTROL_BINDINGS")
    if errors or raw_bindings is None:
        return {}, errors

    bindings: dict[str, dict[str, str]] = {}
    for name, raw_binding in raw_bindings.items():
        if not isinstance(raw_binding, dict):
            errors.append(f"CONTROL_BINDINGS.{name} must be an object")
            continue
        if set(raw_binding) != {"type", "id"}:
            errors.append(
                f"CONTROL_BINDINGS.{name} must contain only type and id"
            )
            continue
        binding_type = raw_binding.get("type")
        control_id = raw_binding.get("id")
        if binding_type not in SUPPORTED_CONTROL_BINDING_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_CONTROL_BINDING_TYPES))
            errors.append(
                f"CONTROL_BINDINGS.{name}.type must be one of: {allowed}"
            )
            continue
        if not isinstance(control_id, str) or not control_id:
            errors.append(f"CONTROL_BINDINGS.{name}.id must be a Stable ID string")
            continue
        bindings[name] = {"type": binding_type, "id": control_id}
    return bindings, errors
