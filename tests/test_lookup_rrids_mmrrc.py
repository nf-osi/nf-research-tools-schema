#!/usr/bin/env python3
"""MMRRC fallback in lookup_rrids.py matches strain names exactly (case- and
whitespace-insensitive), never by fuzzy token overlap. Offline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "lookup_rrids", Path(__file__).resolve().parent.parent / "tool_coverage" / "scripts" / "lookup_rrids.py")
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)


def test_exact_match_only(monkeypatch):
    monkeypatch.setattr(lr, "_MMRRC_CATALOG_CACHE", {
        "b6.129s4-nf1 tm1fcr /j": {"rrid": "RRID:MMRRC_000001-UNC"},
    })
    assert lr._lookup_mmrrc("  B6.129S4-Nf1  tm1Fcr /J ") == "rrid:mmrrc_000001-unc"
    assert lr._lookup_mmrrc("B6.129S4-Nf1 tm1Fcr") == ""  # near-miss: no fuzzy hit
