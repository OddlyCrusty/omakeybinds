"""Non-executing Lua subset and canonical shortcut identities.

Unsupported expressions remain visible but must never be copied into an edit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


MODIFIERS = ("SUPER", "CTRL", "ALT", "SHIFT")
KEY_NAMES = {
    **{f"code:{10 + i}": str((i + 1) % 10) for i in range(10)},
    "code:20": "MINUS", "code:21": "EQUAL", "code:59": "COMMA",
    "code:60": "PERIOD", "code:61": "SLASH", "mouse:272": "LEFT MOUSE BUTTON",
    "mouse:273": "RIGHT MOUSE BUTTON", "mouse:274": "MIDDLE MOUSE BUTTON",
    "mouse_down": "MOUSE WHEEL DOWN", "mouse_up": "MOUSE WHEEL UP",
}


def normalize_key(value: str) -> str:
    tokens = [x.strip() for x in value.split("+")]
    modifiers, keys = set(), []
    for token in tokens:
        upper = token.upper().replace("CONTROL", "CTRL")
        if upper in MODIFIERS:
            modifiers.add(upper)
        elif re.fullmatch(r"(?:code|mouse):\d+|mouse_(?:up|down|left|right)", token, re.I):
            keys.append(token.lower())
        else:
            keys.append(upper)
    if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9_:]+", keys[0]):
        raise ValueError("Unsupported key identifier")
    return " + ".join([m for m in MODIFIERS if m in modifiers] + keys)


def display_key(value: str) -> str:
    parts = value.split(" + ")
    parts[-1] = KEY_NAMES.get(parts[-1], parts[-1])
    return " + ".join(parts)


def lua_string(value: str) -> str:
    # Lua uses decimal escapes, not JSON's \uXXXX escapes. Fixed width avoids
    # swallowing a digit following an escaped control character.
    escaped = []
    for char in value:
        if char in ('"', "\\"):
            escaped.append("\\" + char)
        elif ord(char) < 32 or ord(char) == 127:
            escaped.append(f"\\{ord(char):03d}")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int


def tokens(source: str, comments: bool = False) -> list[Token]:
    result = []
    i = 0
    escapes = dict(zip("abfnrtv", "\a\b\f\n\r\t\v"))
    while i < len(source):
        start = i
        if source[i].isspace():
            i += 1
            continue
        comment = source.startswith("--", i)
        if comment:
            i += 2
        long = re.match(r"\[(=*)\[", source[i:])
        if long:
            begin = i + len(long[0])
            end = source.find("]" + long[1] + "]", begin)
            if end < 0:
                raise ValueError("Unterminated Lua long string/comment")
            value = source[begin:end]
            if value.startswith("\r\n"):
                value = value[2:]
            elif value.startswith(("\n", "\r")):
                value = value[1:]
            i = end + len(long[1]) + 2
            if not comment or comments:
                result.append(Token("comment" if comment else "string", value, start, i))
            continue
        if comment:
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            if comments:
                result.append(Token("comment", source[start:i], start, i))
            continue
        if source[i] in "\"'":
            quote = source[i]
            i += 1
            data = bytearray()
            while i < len(source) and source[i] != quote:
                char = source[i]
                i += 1
                if char in "\r\n":
                    raise ValueError("Unescaped newline in Lua string")
                if char != "\\":
                    data.extend(char.encode("utf-8"))
                    continue
                if i >= len(source):
                    raise ValueError("Unterminated Lua escape")
                char = source[i]
                i += 1
                if char in escapes:
                    data.extend(escapes[char].encode())
                elif char in "\\\"'":
                    data.extend(char.encode())
                elif char in "\r\n":
                    if char == "\r" and source[i:i + 1] == "\n":
                        i += 1
                    data.append(10)
                elif char == "z":
                    while i < len(source) and source[i].isspace():
                        i += 1
                elif char.isascii() and char.isdigit():
                    number = char
                    while len(number) < 3 and i < len(source) and source[i] in "0123456789":
                        number += source[i]
                        i += 1
                    value = int(number)
                    if value > 255:
                        raise ValueError("Invalid Lua byte escape")
                    data.append(value)
                elif char == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", source[i:i + 2]):
                    data.append(int(source[i:i + 2], 16))
                    i += 2
                elif char == "u":
                    match = re.match(r"\{([0-9a-fA-F]+)\}", source[i:])
                    if not match:
                        raise ValueError("Invalid Lua Unicode escape")
                    data.extend(chr(int(match[1], 16)).encode("utf-8"))
                    i += len(match[0])
                else:
                    raise ValueError("Unsupported Lua escape")
            if i >= len(source):
                raise ValueError("Unterminated Lua string")
            i += 1
            result.append(Token("string", data.decode("utf-8"), start, i))
            continue
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", source[i:])
        if match:
            i += len(match[0])
            result.append(Token("name", match[0], start, i))
            continue
        match = re.match(r"(?:\d+(?:\.\d+)?)(?:[eE][+-]?\d+)?", source[i:])
        if match:
            i += len(match[0])
            result.append(Token("number", match[0], start, i))
            continue
        i += 1
        result.append(Token("symbol", source[start:i], start, i))
    return result


def literal_string(value: str) -> str | None:
    try:
        parsed = tokens(value)
        return parsed[0].value if len(parsed) == 1 and parsed[0].kind == "string" else None
    except (ValueError, UnicodeError):
        return None


class Expression:
    def __init__(self, source: str):
        self.items = tokens(source)
        self.index = 0

    def take(self, value: str) -> bool:
        if self.index < len(self.items) and self.items[self.index].value == value and self.items[self.index].kind == "symbol":
            self.index += 1
            return True
        return False

    def need(self, value: str) -> None:
        if not self.take(value):
            raise ValueError("Unsupported expression")

    def value(self, calls: bool = False, depth: int = 0) -> str:
        if depth > 20 or self.index >= len(self.items):
            raise ValueError("Unsupported expression")
        item = self.items[self.index]
        self.index += 1
        if item.kind == "string":
            return lua_string(item.value)
        if item.kind == "number" or (item.kind == "name" and item.value in ("true", "false", "nil")):
            return item.value
        if item.value == "-" and item.kind == "symbol":
            if self.index < len(self.items) and self.items[self.index].kind == "number":
                number = self.items[self.index].value
                self.index += 1
                return "-" + number
            raise ValueError("Unsupported number")
        if item.value == "{" and item.kind == "symbol":
            fields = []
            while not self.take("}"):
                if self.index >= len(self.items):
                    raise ValueError("Unterminated table")
                prefix = ""
                if self.take("["):
                    prefix = "[" + self.value(depth=depth + 1) + "] = "
                    self.need("]")
                    self.need("=")
                elif (self.index + 1 < len(self.items) and self.items[self.index].kind == "name"
                      and self.items[self.index + 1].value == "=" and self.items[self.index + 1].kind == "symbol"):
                    prefix = self.items[self.index].value + " = "
                    self.index += 2
                fields.append(prefix + self.value(depth=depth + 1))
                if self.take("}"):
                    break
                if not (self.take(",") or self.take(";")):
                    raise ValueError("Unsupported table")
            return "{ " + ", ".join(fields) + " }"
        if calls and item.kind == "name" and item.value == "hl":
            names = [item.value]
            while self.take("."):
                if self.index >= len(self.items) or self.items[self.index].kind != "name":
                    raise ValueError("Unsupported dispatcher")
                names.append(self.items[self.index].value)
                self.index += 1
            if len(names) < 3 or names[1] != "dsp":
                raise ValueError("Unsupported dispatcher")
            self.need("(")
            args = []
            if not self.take(")"):
                while True:
                    args.append(self.value(depth=depth + 1))
                    if self.take(")"):
                        break
                    self.need(",")
            return ".".join(names) + "(" + ", ".join(args) + ")"
        raise ValueError("Action depends on unsupported code or local scope")


def safe_expression(source: str, calls: bool = False) -> str:
    parser = Expression(source)
    value = parser.value(calls=calls)
    if parser.index != len(parser.items):
        raise ValueError("Trailing code in expression")
    return value


def binding_spec(action: str, call: str = "o.bind", options: str = "{}") -> dict[str, str]:
    if call not in ("o.bind", "o.bind_toggle"):
        raise ValueError("Unsupported binding type")
    action = safe_expression(action, calls=True)
    if call == "o.bind_toggle" and literal_string(action) is None:
        raise ValueError("Unsupported toggle")
    options = safe_expression(options)
    if not options.startswith("{"):
        raise ValueError("Unsupported binding options")
    return {"action": action, "call": call, "options": options}


def calls(source: str, names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Find calls lexically; never match inside comments or quoted text."""
    items = tokens(source)
    result = []
    index = 0
    while index + 3 < len(items):
        part = items[index:index + 4]
        name = "".join(t.value for t in part[:3])
        if (name not in names or [t.kind for t in part] != ["name", "symbol", "name", "symbol"]
                or part[1].value != "." or part[3].value != "("
                or (index and items[index - 1].kind == "symbol" and items[index - 1].value in (".", ":"))):
            index += 1
            continue
        depth = 1
        end = index + 4
        while end < len(items) and depth:
            if items[end].kind == "symbol":
                depth += (items[end].value == "(") - (items[end].value == ")")
            end += 1
        if depth:
            raise ValueError("Unterminated binding call")
        result.append((name, source[part[3].end:items[end - 1].start]))
        index = end
    return result


def split_arguments(source: str) -> list[str]:
    result, stack = [], []
    start = 0
    for item in tokens(source):
        if item.kind != "symbol":
            continue
        if item.value in "({[":
            stack.append(item.value)
        elif item.value in ")}]":
            if not stack or stack.pop() != dict(zip(")}]", "({["))[item.value]:
                raise ValueError("Unbalanced arguments")
        elif item.value == "," and not stack:
            result.append(source[start:item.start].strip())
            start = item.end
    if stack:
        raise ValueError("Unbalanced arguments")
    result.append(source[start:].strip())
    return result
