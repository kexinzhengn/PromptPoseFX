from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TypeAlias


Primitive: TypeAlias = str | int | float | bool
LiteralValue: TypeAlias = Primitive | None | list["LiteralValue"] | dict[str, "LiteralValue"]

SUPPORTED_CONFIG_TYPES = {"range", "color", "boolean", "select"}
_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")


class ConfigLiteralError(ValueError):
    """Raised when static CONFIG contains unsupported JavaScript syntax."""


@dataclass
class _LiteralParser:
    source: str
    position: int

    def parse(self) -> LiteralValue:
        """Parse one JavaScript literal value without executing generated code."""
        value = self._parse_value()
        self._skip_ignored()
        return value

    def _parse_value(self) -> LiteralValue:
        self._skip_ignored()
        if self.position >= len(self.source):
            raise ConfigLiteralError("CONFIG ended before its value was complete")

        current = self.source[self.position]
        if current == "{":
            return self._parse_object()
        if current == "[":
            return self._parse_array()
        if current in {"'", '"'}:
            return self._parse_string()

        number_match = _NUMBER_RE.match(self.source, self.position)
        if number_match:
            token = number_match.group(0)
            self.position = number_match.end()
            return float(token) if any(marker in token for marker in ".eE") else int(token)

        identifier = self._parse_identifier()
        if identifier == "true":
            return True
        if identifier == "false":
            return False
        if identifier == "null":
            return None
        raise ConfigLiteralError(
            "CONFIG values must use static literal values; dynamic expressions are unsupported"
        )

    def _parse_object(self) -> dict[str, LiteralValue]:
        result: dict[str, LiteralValue] = {}
        self._expect("{")
        self._skip_ignored()
        if self._consume("}"):
            return result

        while True:
            self._skip_ignored()
            if self.position < len(self.source) and self.source[self.position] in {"'", '"'}:
                key = self._parse_string()
            else:
                key = self._parse_identifier()
            if not isinstance(key, str) or not key:
                raise ConfigLiteralError("CONFIG object keys must be non-empty strings")
            if key in result:
                raise ConfigLiteralError(f"CONFIG contains the duplicate key {key!r}")

            self._skip_ignored()
            self._expect(":")
            result[key] = self._parse_value()
            self._skip_ignored()
            if self._consume("}"):
                return result
            self._expect(",")
            self._skip_ignored()
            if self._consume("}"):
                return result

    def _parse_array(self) -> list[LiteralValue]:
        result: list[LiteralValue] = []
        self._expect("[")
        self._skip_ignored()
        if self._consume("]"):
            return result

        while True:
            result.append(self._parse_value())
            self._skip_ignored()
            if self._consume("]"):
                return result
            self._expect(",")
            self._skip_ignored()
            if self._consume("]"):
                return result

    def _parse_string(self) -> str:
        quote = self.source[self.position]
        self.position += 1
        output: list[str] = []
        escapes = {
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "0": "\0",
            "\\": "\\",
            "'": "'",
            '"': '"',
        }

        while self.position < len(self.source):
            current = self.source[self.position]
            self.position += 1
            if current == quote:
                return "".join(output)
            if current != "\\":
                if current in "\r\n":
                    raise ConfigLiteralError("CONFIG strings cannot contain an unescaped newline")
                output.append(current)
                continue
            if self.position >= len(self.source):
                break

            escaped = self.source[self.position]
            self.position += 1
            if escaped in escapes:
                output.append(escapes[escaped])
                continue
            if escaped in {"u", "x"}:
                length = 4 if escaped == "u" else 2
                digits = self.source[self.position:self.position + length]
                if len(digits) != length or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                    raise ConfigLiteralError("CONFIG contains an invalid string escape")
                output.append(chr(int(digits, 16)))
                self.position += length
                continue
            output.append(escaped)

        raise ConfigLiteralError("CONFIG contains an unterminated string")

    def _parse_identifier(self) -> str:
        match = _IDENTIFIER_RE.match(self.source, self.position)
        if match is None:
            raise ConfigLiteralError(
                f"CONFIG contains an unsupported token near position {self.position}"
            )
        self.position = match.end()
        return match.group(0)

    def _skip_ignored(self) -> None:
        while self.position < len(self.source):
            if self.source[self.position].isspace():
                self.position += 1
                continue
            if self.source.startswith("//", self.position):
                newline = self.source.find("\n", self.position + 2)
                self.position = len(self.source) if newline < 0 else newline + 1
                continue
            if self.source.startswith("/*", self.position):
                closing = self.source.find("*/", self.position + 2)
                if closing < 0:
                    raise ConfigLiteralError("CONFIG contains an unterminated block comment")
                self.position = closing + 2
                continue
            return

    def _consume(self, token: str) -> bool:
        if self.source.startswith(token, self.position):
            self.position += len(token)
            return True
        return False

    def _expect(self, token: str) -> None:
        if not self._consume(token):
            raise ConfigLiteralError(
                f"CONFIG expected {token!r} near position {self.position}"
            )


def validate_static_config(code: str) -> tuple[dict[str, dict[str, LiteralValue]], list[str]]:
    """Parse and validate the complete static CONFIG contract."""
    executable = _mask_comments_and_strings(code)
    match = re.search(r"static\s+CONFIG\s*=\s*", executable)
    if match is None:
        return {}, ["Missing static CONFIG definition"]

    try:
        parsed = _LiteralParser(code, match.end()).parse()
    except ConfigLiteralError as error:
        return {}, [f"Invalid static CONFIG: {error}"]

    if not isinstance(parsed, dict):
        return {}, ["static CONFIG must be an object literal"]

    config: dict[str, dict[str, LiteralValue]] = {}
    errors: list[str] = []
    for param_name, raw_metadata in parsed.items():
        prefix = f"CONFIG.{param_name}"
        if not isinstance(raw_metadata, dict):
            errors.append(f"{prefix} must be an object")
            continue
        config[param_name] = raw_metadata
        errors.extend(_validate_param(prefix, raw_metadata))

    return config, errors


def parse_static_object_literal(
    code: str,
    property_name: str,
) -> tuple[dict[str, LiteralValue] | None, list[str]]:
    """Parse one optional static object property without executing JavaScript."""
    executable = _mask_comments_and_strings(code)
    match = re.search(
        rf"static\s+{re.escape(property_name)}\s*=\s*",
        executable,
    )
    if match is None:
        return None, []
    try:
        parsed = _LiteralParser(code, match.end()).parse()
    except ConfigLiteralError as error:
        return None, [f"Invalid static {property_name}: {error}"]
    if not isinstance(parsed, dict):
        return None, [f"static {property_name} must be an object literal"]
    return parsed, []


def _validate_param(prefix: str, metadata: dict[str, LiteralValue]) -> list[str]:
    """Validate common metadata and the selected control's specific fields."""
    errors: list[str] = []
    for field_name in ("default", "type", "label", "description"):
        if field_name not in metadata:
            errors.append(f"{prefix} is missing a {field_name} field")

    param_type = metadata.get("type")
    if not isinstance(param_type, str) or param_type not in SUPPORTED_CONFIG_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_CONFIG_TYPES))
        errors.append(f"{prefix}.type must be one of: {allowed}")

    for field_name in ("label", "description"):
        value = metadata.get(field_name)
        if not _is_english_ui_text(value):
            errors.append(f"{prefix}.{field_name} must be non-empty English text")

    if "default" in metadata and not _is_primitive(metadata["default"]):
        errors.append(f"{prefix}.default must be a string, finite number, or boolean literal")

    if param_type == "range":
        errors.extend(_validate_range(prefix, metadata))
    elif param_type == "color":
        default = metadata.get("default")
        if not isinstance(default, str) or _COLOR_RE.fullmatch(default) is None:
            errors.append(f"{prefix}.default must be a #RRGGBB color")
    elif param_type == "boolean":
        if not isinstance(metadata.get("default"), bool):
            errors.append(f"{prefix}.default must be a boolean")
    elif param_type == "select":
        errors.extend(_validate_select(prefix, metadata))

    return errors


def _validate_range(prefix: str, metadata: dict[str, LiteralValue]) -> list[str]:
    errors: list[str] = []
    for field_name in ("default", "min", "max", "step"):
        if field_name not in metadata:
            errors.append(f"{prefix} is missing a {field_name} field")
        elif not _is_number(metadata[field_name]):
            errors.append(f"{prefix}.{field_name} must be a finite number")

    default = metadata.get("default")
    minimum = metadata.get("min")
    maximum = metadata.get("max")
    step = metadata.get("step")
    if _is_number(minimum) and _is_number(maximum) and minimum >= maximum:
        errors.append(f"{prefix}.min must be less than max")
    if _is_number(step) and step <= 0:
        errors.append(f"{prefix}.step must be greater than zero")
    if (
        _is_number(default)
        and _is_number(minimum)
        and _is_number(maximum)
        and not minimum <= default <= maximum
    ):
        errors.append(f"{prefix}.default must be between min and max")
    return errors


def _validate_select(prefix: str, metadata: dict[str, LiteralValue]) -> list[str]:
    options = metadata.get("options")
    if not isinstance(options, list) or not options:
        return [f"{prefix}.options must be a non-empty array"]

    errors: list[str] = []
    identities: set[tuple[str, Primitive]] = set()
    for index, option in enumerate(options):
        option_prefix = f"{prefix}.options[{index}]"
        if not isinstance(option, dict):
            errors.append(f"{option_prefix} must be an object")
            continue
        if "label" not in option:
            errors.append(f"{option_prefix} is missing a label field")
        elif not _is_english_ui_text(option["label"]):
            errors.append(f"{option_prefix}.label must be non-empty English text")
        if "value" not in option:
            errors.append(f"{option_prefix} is missing a value field")
            continue
        value = option["value"]
        if not _is_primitive(value):
            errors.append(f"{option_prefix}.value must be a primitive literal")
            continue
        identity = _primitive_identity(value)
        if identity in identities:
            errors.append(f"{prefix}.options values must be unique")
        identities.add(identity)

    default = metadata.get("default")
    if _is_primitive(default) and _primitive_identity(default) not in identities:
        errors.append(f"{prefix}.default must match one option value with the same type")
    return errors


def _is_english_ui_text(value: LiteralValue | None) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and re.search(r"[A-Za-z]", value) is not None
        and not any(character.isalpha() and not character.isascii() for character in value)
    )


def _is_number(value: LiteralValue | None) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_primitive(value: LiteralValue | None) -> bool:
    return isinstance(value, (str, bool)) or _is_number(value)


def _primitive_identity(value: Primitive) -> tuple[str, Primitive]:
    if isinstance(value, bool):
        return "boolean", value
    if _is_number(value):
        return "number", value
    return "string", value


def _mask_comments_and_strings(source: str) -> str:
    """Preserve code positions while hiding fake declarations in literal text."""
    output = list(source)
    position = 0

    def mask(start: int, end: int) -> None:
        for index in range(start, end):
            if output[index] not in "\r\n":
                output[index] = " "

    while position < len(source):
        if source.startswith("//", position):
            end = source.find("\n", position + 2)
            end = len(source) if end < 0 else end
            mask(position, end)
            position = end
            continue
        if source.startswith("/*", position):
            closing = source.find("*/", position + 2)
            end = len(source) if closing < 0 else closing + 2
            mask(position, end)
            position = end
            continue
        if source[position] in {"'", '"', "`"}:
            quote = source[position]
            start = position
            position += 1
            while position < len(source):
                if source[position] == "\\":
                    position += 2
                    continue
                if source[position] == quote:
                    position += 1
                    break
                position += 1
            mask(start, min(position, len(source)))
            continue
        position += 1

    return "".join(output)
