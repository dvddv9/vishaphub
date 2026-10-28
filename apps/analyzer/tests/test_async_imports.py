# -*- coding: utf-8 -*-
"""Regression: async pipeline imports all needed config constants.

Bug v5.8-v5.10.4: async_stages.py used MAX_TOKENS_STAGE4 without import.
"""
import ast
from pathlib import Path


def _get_used_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    return names


def _get_imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _get_defined_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _get_config_names():
    tree = ast.parse(Path("src/config.py").read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    names.add(t.id)
    return names


def test_async_stages_imports_all_config_constants_used():
    tree = ast.parse(Path("src/pipeline/async_stages.py").read_text(encoding="utf-8"))
    used = _get_used_names(tree)
    imported = _get_imported_names(tree)
    defined = _get_defined_names(tree)
    config_names = _get_config_names()
    missing = (used & config_names) - imported - defined
    assert not missing, f"async_stages.py uses config constants without import: {missing}"


def test_stages_imports_all_config_constants_used():
    tree = ast.parse(Path("src/pipeline/stages.py").read_text(encoding="utf-8"))
    used = _get_used_names(tree)
    imported = _get_imported_names(tree)
    defined = _get_defined_names(tree)
    config_names = _get_config_names()
    missing = (used & config_names) - imported - defined
    assert not missing, f"stages.py uses config constants without import: {missing}"


def test_max_tokens_stage4_defined_in_config():
    assert "MAX_TOKENS_STAGE4" in _get_config_names()


def test_async_stages_imports_max_tokens_stage4():
    src = Path("src/pipeline/async_stages.py").read_text(encoding="utf-8")
    assert "MAX_TOKENS_STAGE4" in src
    tree = ast.parse(src)
    assert "MAX_TOKENS_STAGE4" in _get_imported_names(tree)
