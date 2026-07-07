"""Extractability invariant: nothing under ``termcade.core`` may import textual.

Keeping the core TUI-agnostic is what lets it be unit-tested without a TTY and
extracted later. This test AST-walks every core module and fails on a textual import.
"""

from __future__ import annotations

import ast
import pathlib

import termcade.core as core_pkg

CORE_DIR = pathlib.Path(core_pkg.__file__).resolve().parent


def _imported_modules(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_core_never_imports_textual():
    offenders = []
    for py_file in CORE_DIR.rglob("*.py"):
        for module in _imported_modules(py_file):
            if module == "textual" or module.startswith("textual."):
                offenders.append(f"{py_file.name} imports {module}")
    assert not offenders, "core must stay TUI-agnostic: " + "; ".join(offenders)
