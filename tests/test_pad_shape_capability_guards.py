# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""All custom shape resolvers are gated, including board/generic readers.

Source mutation tests prove removal of each gate is caught. Native Altium
validation remains necessary: Python cannot emulate SDK identifier binding.
"""
from pathlib import Path
import re

import pytest

from tests.pascal_source import functions, strip_comments

ROOT = Path(__file__).resolve().parents[1] / "scripts/altium"
FILES = ("Library.pas", "PCBGeneric.pas", "PCB.pas", "Generic.pas")


def source(name):
    return strip_comments((ROOT / name).read_text(encoding="utf-8"))


def check_resolvers(text):
    uses = list(re.finditer(r"\beCustomShape\b", text))
    assert uses, "no custom shape references found"
    for use in uses:
        # A separate nested statement, not And/Or: DelphiScript need not
        # short circuit, and an unresolved identifier bypasses Try/Except.
        assert re.search(
            r"If PadCustomShapeSupported\(0\) Then\s+If (?:Pad\.TopShape|S) = $",
            text[max(0, use.start() - 120):use.start()]), "unguarded custom shape"
    return len(uses)


def check_capabilities(text):
    routines = functions(text)
    for name, minimum in (("PadCustomShapeSupported", 25), ("PadAdvancedMaskSupported", 25)):
        body = routines[name]
        assert "Client.GetProductVersion" in body
        assert "Major := 0;" in body
        assert "StrToIntDef(Copy(Ver, 1, Pos('.', Ver) - 1), 0)" in body
        assert f"Result := Major >= {minimum};" in body
        assert "eCustomShape" not in body


def test_independent_capabilities_live_in_early_shared_unit():
    check_capabilities(source("Utils.pas"))
    build = (ROOT / "build.py").read_text(encoding="utf-8")
    for name in FILES:
        assert build.index("'Utils.pas'") < build.index(repr(name))
    assert "LibraryAdvancedPadApiSupported" not in source("Library.pas")


def test_every_shape_resolver_is_guarded():
    counts = [check_resolvers(source(name)) for name in FILES]
    assert counts == [4, 1, 2, 1], "update expected coverage when adding a reader"


@pytest.mark.parametrize("filename", FILES)
def test_removing_any_gate_is_detected(filename):
    text = source(filename)
    gates = list(re.finditer(r"If PadCustomShapeSupported\(0\) Then", text))
    assert gates
    for gate in gates:
        broken = text[:gate.start()] + text[gate.end():]
        with pytest.raises(AssertionError, match="unguarded custom shape"):
            check_resolvers(broken)


@pytest.mark.parametrize("name", ["PadCustomShapeSupported", "PadAdvancedMaskSupported"])
@pytest.mark.parametrize("minimum", [24, 26])
def test_changing_either_measured_capability_floor_is_detected(name, minimum):
    text = source("Utils.pas")
    body = functions(text)[name]
    broken = text.replace(body, body.replace("Major >= 25", f"Major >= {minimum}"))
    assert broken != text
    with pytest.raises(AssertionError):
        check_capabilities(broken)


def test_unknown_shape_is_not_reported_as_round():
    for filename in FILES:
        text = source(filename)
        uses = list(re.finditer(r"\beCustomShape\b", text))
        assert uses
        for use in uses:
            # Restrict this check to the shape branch. The enclosing generic
            # getter also has legitimate round defaults for drill geometry.
            before = text[max(0, use.start() - 1200):use.start()]
            assert re.search(r"If (?:Pad\.TopShape|S) = eRounded Then", before)
            assert re.search(r"(?:ShapeStr|Str|Result|Name) := '(?:unknown|Unknown|Other)';", before)
            after = text[use.end():use.end() + 120]
            assert not re.search(r"Else (?:ShapeStr|Str|Result|Name) := '[Rr]ound';", after)
