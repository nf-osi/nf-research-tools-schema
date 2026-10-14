#!/usr/bin/env python3
"""Every Python script the workflows run must at least compile. Most aren't
imported by any test, so a syntax error otherwise only shows up mid-upsert
(analyze_missing_tools.py broke #187's run this way)."""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(
    p for p in REPO_ROOT.rglob("*.py")
    if ".git" not in p.parts and "node_modules" not in p.parts
)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_compiles(path):
    py_compile.compile(str(path), doraise=True)
