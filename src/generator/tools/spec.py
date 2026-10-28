"""Load and validate spec.yaml.

Every error names the field and, where it can, the line in the file.
Lines come from the YAML node tree, not from list indexes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SUPPORTED_VERSION = 1
MAX_TEXT = 20_000
MAX_RULE_TEXT = 500

KNOWN_KEYS = frozenset({
    "version", "updated", "text", "target", "kind", "output",
    "inputs", "outputs", "profile", "constraints",
    "must_never", "should", "may", "check", "caller", "route",
})
REQUIREMENT_LISTS = ("inputs", "outputs", "must_never", "should", "may")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PARAM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
IN_VALUES = frozenset({"query", "path", "body", "header"})
PROFILES = frozenset({"none", "owasp-asvs-1", "owasp-asvs-2"})
CHECKS = frozenset({"analyzer", "none"})
KINDS = frozenset({"function", "http-endpoint", "module", "config"})
CONSTRAINTS = frozenset({"include-tests", "validate-inputs", "no-dependencies", "explain-decisions"})
CALLERS = frozenset({"public", "signed-in", "internal"})
MAX_OUTPUT_PATH = 200
DRIVE_RE = re.compile(r"^[A-Za-z]:")
ROUTE_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9_\-./{}<>:]*)$")

ITEM_KEYS = {
    "inputs": frozenset({"name", "in", "rule"}),
    "outputs": frozenset({"status", "body", "when"}),
    "must_never": frozenset({"id", "text"}),
    "should": frozenset({"id", "text"}),
    "may": frozenset({"id", "text"}),
}


class SpecError(ValueError):
    """A spec problem. `line` is 1-based, or None when the whole file is at fault."""

    def __init__(self, field: str, line: int | None, message: str):
        self.field = field
        self.line = line
        self.message = message
        where = f"line {line}" if line else "file"
        super().__init__(f"{where}: {field}: {message}")


@dataclass(frozen=True)
class Spec:
    path: str
    sha256: str
    version: int
    updated: dt.date
    text: str
    data: dict
    # field name -> list of (item, 1-based line)
    items: dict
    # top-level key -> 1-based line
    key_lines: dict


def _key_line(root: yaml.MappingNode, key: str) -> int | None:
    for k_node, _ in root.value:
        if k_node.value == key:
            return k_node.start_mark.line + 1
    return None


def _value_node(root: yaml.MappingNode, key: str):
    for k_node, v_node in root.value:
        if k_node.value == key:
            return v_node
    return None


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _check_top_level(data: dict, root: yaml.MappingNode) -> None:
    seen: set[str] = set()
    for k_node, _ in root.value:
        key = str(k_node.value)
        if key in seen:
            raise SpecError(key, k_node.start_mark.line + 1, "duplicate key")
        seen.add(key)

    for key in data:
        if key not in KNOWN_KEYS:
            raise SpecError(str(key), _key_line(root, key), "unknown key")

    if "version" not in data:
        raise SpecError("version", None, "required")
    if not _is_int(data["version"]) or data["version"] != SUPPORTED_VERSION:
        raise SpecError("version", _key_line(root, "version"),
                        f"must be {SUPPORTED_VERSION}")

    if "updated" not in data:
        raise SpecError("updated", None, "required")
    updated = data["updated"]
    if isinstance(updated, dt.datetime) or not isinstance(updated, dt.date):
        raise SpecError("updated", _key_line(root, "updated"),
                        "use an ISO date, YYYY-MM-DD")

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise SpecError("text", _key_line(root, "text") if "text" in data else None,
                        "required, non-empty text")
    if len(text) > MAX_TEXT:
        raise SpecError("text", _key_line(root, "text"),
                        f"longer than {MAX_TEXT} characters")

    for name, allowed in (("profile", PROFILES), ("check", CHECKS), ("kind", KINDS),
                          ("caller", CALLERS)):
        if name in data and data[name] not in allowed:
            raise SpecError(name, _key_line(root, name),
                            f"must be one of: {', '.join(sorted(allowed))}")

    for name in ("target", "output"):
        if name in data and not (isinstance(data[name], str) and data[name].strip()):
            raise SpecError(name, _key_line(root, name), "must be a non-empty string")

    if "output" in data:
        _check_output_path(data["output"], _key_line(root, "output"))

    if "route" in data:
        if not isinstance(data["route"], str) or not ROUTE_RE.match(data["route"]):
            raise SpecError("route", _key_line(root, "route"),
                            "must look like: GET /user")

    if "constraints" in data:
        cons = data["constraints"]
        if not isinstance(cons, list):
            raise SpecError("constraints", _key_line(root, "constraints"), "must be a list")
        for c in cons:
            if c not in CONSTRAINTS:
                raise SpecError("constraints", _key_line(root, "constraints"),
                                f"unknown constraint {c!r}")


def _check_output_path(path: str, line: int | None) -> None:
    """The output path is relative, forward-slashed and never leaves its folder."""
    if len(path) > MAX_OUTPUT_PATH:
        raise SpecError("output", line, f"longer than {MAX_OUTPUT_PATH} characters")
    if "\\" in path:
        raise SpecError("output", line, "use forward slashes")
    if path.startswith("/") or DRIVE_RE.match(path):
        raise SpecError("output", line, "must be a relative path")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise SpecError("output", line, "no empty, '.' or '..' parts")


def _list_items(data: dict, root: yaml.MappingNode, field: str) -> list[tuple[dict, int]]:
    if field not in data:
        return []
    value = data[field]
    node = _value_node(root, field)
    line = _key_line(root, field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(field, line, "must be a list")

    out: list[tuple[dict, int]] = []
    for index, item in enumerate(value):
        item_line = node.value[index].start_mark.line + 1 if node is not None else line
        if not isinstance(item, dict):
            raise SpecError(field, item_line, "each entry must be a mapping")
        allowed = ITEM_KEYS[field]
        for k in item:
            if k not in allowed:
                raise SpecError(field, item_line, f"unknown key {k!r}")
        out.append((item, item_line))
    return out


def _check_inputs(items: list[tuple[dict, int]]) -> None:
    for item, line in items:
        name = item.get("name")
        if not isinstance(name, str) or not PARAM_RE.match(name):
            raise SpecError("inputs", line, "name must be an identifier")
        if item.get("in") not in IN_VALUES:
            raise SpecError("inputs", line,
                            f"in must be one of: {', '.join(sorted(IN_VALUES))}")
        if "rule" in item and not (isinstance(item["rule"], str) and item["rule"].strip()):
            raise SpecError("inputs", line, "rule must be a non-empty string")


def _check_outputs(items: list[tuple[dict, int]]) -> None:
    for item, line in items:
        status = item.get("status")
        if not _is_int(status) or not 100 <= status <= 599:
            raise SpecError("outputs", line, "status must be an HTTP code, 100-599")
        if not (item.get("body") or item.get("when")):
            raise SpecError("outputs", line, "needs body or when")
        for k in ("body", "when"):
            if k in item and not (isinstance(item[k], str) and item[k].strip()):
                raise SpecError("outputs", line, f"{k} must be a non-empty string")


def _check_rules(field: str, items: list[tuple[dict, int]], seen_ids: dict) -> None:
    for item, line in items:
        rid = item.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid):
            raise SpecError(field, line,
                            "id must be lowercase letters, digits and dashes")
        if rid in seen_ids:
            raise SpecError(field, line,
                            f"duplicate id {rid!r} (also in {seen_ids[rid]})")
        seen_ids[rid] = field
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SpecError(field, line, "text must be a non-empty string")
        if len(text) > MAX_RULE_TEXT:
            raise SpecError(field, line, f"text longer than {MAX_RULE_TEXT} characters")


def load_spec(path: str | Path) -> Spec:
    p = Path(path)
    raw = p.read_bytes()
    try:
        text_src = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SpecError("file", None, f"not UTF-8: {e}") from e

    try:
        root = yaml.compose(text_src, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text_src)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        problem = getattr(e, "problem", None) or str(e)
        raise SpecError("file", line, f"invalid YAML: {problem}") from e

    if not isinstance(root, yaml.MappingNode) or not isinstance(data, dict):
        raise SpecError("file", 1, "top level must be a mapping")

    _check_top_level(data, root)

    items: dict[str, list[tuple[dict, int]]] = {}
    for field in REQUIREMENT_LISTS:
        items[field] = _list_items(data, root, field)

    _check_inputs(items["inputs"])
    _check_outputs(items["outputs"])
    seen_ids: dict[str, str] = {}
    for field in ("must_never", "should", "may"):
        _check_rules(field, items[field], seen_ids)

    total = sum(len(items[f]) for f in REQUIREMENT_LISTS)
    if total == 0:
        raise SpecError("file", None,
                        "no requirements: add inputs, outputs or must_never")

    return Spec(
        path=str(p),
        sha256=hashlib.sha256(raw).hexdigest(),
        version=data["version"],
        updated=data["updated"],
        text=data["text"],
        data=data,
        items=items,
        key_lines={str(k.value): k.start_mark.line + 1 for k, _ in root.value},
    )
