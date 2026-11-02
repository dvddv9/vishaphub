# -*- coding: utf-8 -*-
"""Bounded inter-file Python taint analysis for repository scans.

This is a conservative, syntax-only pass. It resolves local Python imports, computes
function summaries to a fixed point, and follows values from configured sources into
configured sinks through positional call arguments and simple assignments. It does not
execute imports, resolve dynamic dispatch, or claim coverage for other languages.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from src.tools.patterns import AST_TAINT_SINKS, AST_TAINT_SOURCES

MAX_PROJECT_FILES = 2_000
MAX_FUNCTIONS = 8_000
MAX_SUMMARY_ROUNDS = 24

_SINK_CWE = {"sql_execute": "CWE-89", "cmd_exec": "CWE-78", "file_write": "CWE-22"}
_SOURCE_PREFIXES = tuple(p for values in AST_TAINT_SOURCES.values() for p in values if p != "open")
_SINK_PREFIXES = tuple((group, p) for group, values in AST_TAINT_SINKS.items() for p in values)


def _dotted(node: ast.AST) -> str:
    try:
        return ast.unparse(node.func if isinstance(node, ast.Call) else node)
    except Exception:
        return ""


def _module_for(path: str) -> str:
    p = PurePosixPath(path)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_call(node: ast.Call) -> bool:
    dotted = _dotted(node)
    return any(dotted == prefix or dotted.startswith(prefix + ".") for prefix in _SOURCE_PREFIXES)


def _sink_call(node: ast.Call) -> str | None:
    dotted = _dotted(node)
    for group, prefix in _SINK_PREFIXES:
        if dotted == prefix or dotted.endswith("." + prefix) or dotted.startswith(prefix + "."):
            return group
    return None


@dataclass
class Unit:
    key: str
    file: str
    module: str
    name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    params: tuple[str, ...]
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)
    # param index -> sink id -> shortest call chain from this function to that sink
    sinks: dict[int, dict[tuple[str, int, str], tuple[tuple[str, int, str], ...]]] = field(default_factory=dict)
    returns: set[int] = field(default_factory=set)


def _resolve_relative(module: str, level: int, imported: str | None) -> str:
    package = module.rpartition(".")[0]
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[:max(0, len(parts) - level + 1)]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(p for p in parts if p)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _target_for(unit: Unit, call: ast.Call, modules: dict[str, str], functions: dict[str, Unit]) -> Unit | None:
    dotted = _dotted(call)
    if not dotted:
        return None
    head, _, tail = dotted.partition(".")
    binding = unit.imports.get(head)
    candidates: list[str] = []
    if binding:
        kind, value = binding
        if kind == "function":
            candidates.append(value)
            if tail:
                candidates.append(f"{value}.{tail}")
        elif kind == "module" and tail:
            candidates.append(f"{value}.{tail}")
    candidates.extend((f"{unit.module}.{dotted}", dotted))
    # An imported class instance or a method called through self is resolved only
    # when exactly one local method has this name; ambiguity stays unresolved.
    if "." in dotted and not binding:
        method = dotted.rsplit(".", 1)[-1]
        matches = [k for k, f in functions.items() if f.name == method and f.module == unit.module]
        if len(matches) == 1:
            candidates.append(matches[0])
    for candidate in candidates:
        key = modules.get(candidate, candidate)
        if key in functions:
            return functions[key]
    return None


def _arg_labels(node: ast.AST, env: dict[str, set[tuple]], source_mode: bool) -> set[tuple]:
    labels: set[tuple] = set()
    for name in _names(node):
        labels.update(env.get(name, set()))
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _source_call(child):
            if source_mode:
                labels.add(("source", getattr(child, "lineno", 0)))
    return labels


def _walk_statements(nodes: list[ast.stmt]):
    """Walk executable statements without crossing into nested function scopes."""
    for node in nodes:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        for field_name in ("body", "orelse", "finalbody"):
            children = getattr(node, field_name, None)
            if isinstance(children, list):
                yield from _walk_statements(children)
        for handler in getattr(node, "handlers", ()) or ():
            yield from _walk_statements(handler.body)


def _units(files: dict[str, str]) -> tuple[list[Unit], dict[str, Unit], dict[str, str]]:
    modules: dict[str, str] = {}
    parsed: dict[str, tuple[str, ast.Module]] = {}
    for file, text in sorted(files.items()):
        if not file.endswith(".py"):
            continue
        module = _module_for(file)
        modules[module] = file
        try:
            parsed[file] = (module, ast.parse(text))
        except (SyntaxError, ValueError):
            continue

    units: list[Unit] = []
    by_key: dict[str, Unit] = {}
    for file, (module, tree) in parsed.items():
        import_map: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    import_map[local] = ("module", alias.name if alias.asname else alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                target_module = (_resolve_relative(module, node.level, node.module) if node.level
                                 else (node.module or ""))
                for alias in node.names:
                    if alias.name != "*":
                        import_map[alias.asname or alias.name] = ("function", f"{target_module}.{alias.name}")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parents = [p.name for p in ast.walk(tree) if isinstance(p, ast.ClassDef)
                       and p.lineno < node.lineno <= getattr(p, "end_lineno", p.lineno)]
            qualname = ".".join((module, *(parents[-1:] if parents else ()), node.name))
            args = [*node.args.posonlyargs, *node.args.args]
            if args and args[0].arg in ("self", "cls"):
                args = args[1:]
            params = tuple(a.arg for a in args)
            unit = Unit(qualname, file, module, node.name, node, params, import_map)
            units.append(unit)
            by_key[qualname] = unit
            # Short module.function lookup supports simple `from module import fn`.
            by_key.setdefault(f"{module}.{node.name}", unit)
    module_index = {name: file for name, file in modules.items()}
    return units[:MAX_FUNCTIONS], by_key, module_index


def _analyse_unit(unit: Unit, functions: dict[str, Unit], modules: dict[str, str], *, source_mode: bool = False):
    env: dict[str, set[tuple]] = {name: {("param", i)} for i, name in enumerate(unit.params)}
    sinks: dict[int, dict[tuple[str, int, str], tuple[tuple[str, int, str], ...]]] = {}
    returned: set[int] = set()
    source_hits: list[tuple[int, tuple[str, int, str], tuple[tuple[str, int, str], ...]]] = []

    def eval_call(call: ast.Call) -> set[tuple]:
        arg_sets = [_arg_labels(arg, env, source_mode) for arg in call.args]
        target = _target_for(unit, call, modules, functions)
        argument_map = {index: labels for index, labels in enumerate(arg_sets)}
        if target:
            for keyword in call.keywords:
                if keyword.arg in target.params:
                    argument_map[target.params.index(keyword.arg)] = _arg_labels(keyword.value, env, source_mode)
        labels = set().union(*argument_map.values()) if argument_map else set()
        if _source_call(call) and source_mode:
            labels.add(("source", getattr(call, "lineno", 0)))
        group = _sink_call(call)
        if group:
            for label in labels:
                if label[0] == "param":
                    sink_id = (unit.file, getattr(call, "lineno", 0), group)
                    sinks.setdefault(label[1], {}).setdefault(sink_id, ())
                elif label[0] == "source":
                    sink_id = (unit.file, getattr(call, "lineno", 0), group)
                    source_hits.append((label[1], sink_id, ()))
        if target:
            call_edge = (unit.file, getattr(call, "lineno", 0), target.key)
            for p_index, arg_labels in argument_map.items():
                for label in arg_labels:
                    if label[0] == "param":
                        for sink_id, chain in target.sinks.get(p_index, {}).items():
                            trace = (call_edge, *chain)
                            old = sinks.setdefault(label[1], {}).get(sink_id)
                            if old is None or len(trace) < len(old):
                                sinks[label[1]][sink_id] = trace
                    elif label[0] == "source":
                        for sink_id, chain in target.sinks.get(p_index, {}).items():
                            source_hits.append((label[1], sink_id, (call_edge, *chain)))
            returned_labels = set()
            for p_index in target.returns:
                returned_labels.update(argument_map.get(p_index, set()))
            labels.update(returned_labels)
        return labels

    def expression(node: ast.AST) -> set[tuple]:
        if isinstance(node, ast.Name):
            return set(env.get(node.id, set()))
        if isinstance(node, ast.Call):
            labels: set[tuple] = set()
            # Inner calls first so `helper(source())` retains the source marker.
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Call):
                    labels.update(expression(child))
            return labels | eval_call(node)
        labels: set[tuple] = set()
        for child in ast.iter_child_nodes(node):
            labels.update(expression(child))
        return labels

    for statement in _walk_statements(unit.node.body):
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = getattr(statement, "value", None)
            if value is None:
                continue
            labels = expression(value)
            targets = getattr(statement, "targets", [getattr(statement, "target", None)])
            for target in targets:
                if isinstance(target, ast.Name):
                    env[target.id] = set(labels)
        elif isinstance(statement, ast.Return) and statement.value is not None:
            for label in expression(statement.value):
                if label[0] == "param":
                    returned.add(label[1])
        elif isinstance(statement, ast.Expr):
            expression(statement.value)
    return sinks, returned, source_hits


def analyze_project(files: dict[str, str]) -> list[dict]:
    """Find source-to-sink flows crossing Python file boundaries in a project snapshot."""
    if not isinstance(files, dict) or len(files) > MAX_PROJECT_FILES:
        return []
    units, functions, modules = _units(files)
    if not units:
        return []

    # Function summaries are monotone; the round bound keeps recursive import graphs cheap.
    for _ in range(MAX_SUMMARY_ROUNDS):
        changed = False
        for unit in units:
            sinks, returned, _ = _analyse_unit(unit, functions, modules)
            for p_index, paths in sinks.items():
                old_paths = unit.sinks.setdefault(p_index, {})
                for sink_id, chain in paths.items():
                    old = old_paths.get(sink_id)
                    if old is None or len(chain) < len(old):
                        old_paths[sink_id] = chain
                        changed = True
            new_returns = unit.returns | returned
            if new_returns != unit.returns:
                unit.returns = new_returns
                changed = True
        if not changed:
            break

    found: dict[tuple[str, int, str, int], dict] = {}
    for unit in units:
        _, _, hits = _analyse_unit(unit, functions, modules, source_mode=True)
        for source_line, (sink_file, sink_line, group), chain in hits:
            if unit.file == sink_file and not any(edge[0] != sink_file for edge in chain):
                continue
            key = (unit.file, source_line, sink_file, sink_line)
            path = [{"file": unit.file, "line": source_line, "type": "source"}]
            path.extend({"file": file, "line": line, "type": "call", "target": target}
                        for file, line, target in chain)
            path.append({"file": sink_file, "line": sink_line, "type": "sink"})
            finding = {"id": "taint-cross-file", "title": "Untrusted data reaches a sensitive call across files",
                       "severity": "high", "cwe": _SINK_CWE.get(group, "CWE-20"), "kind": "security",
                       "file": sink_file, "line": sink_line, "snippet": f"source: {unit.file}:{source_line}",
                       "fix": "Validate or encode the value at the boundary, or use a safe API.", "taint_path": path}
            prior = found.get(key)
            if prior is None or len(path) < len(prior["taint_path"]):
                found[key] = finding
    return sorted(found.values(), key=lambda f: (f["file"], f["line"], f["cwe"]))
