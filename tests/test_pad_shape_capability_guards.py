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


def check_capabilities(text):
    routines = functions(text)
    assert re.findall(r"(?im)^Function\s+PadCustomShapeSupported\b", text) == [
        "Function PadCustomShapeSupported"]
    assert "Result := AltiumVersionCode(0) >= 2208;" in routines["PadCustomShapeSupported"]
    body = routines["PadAdvancedMaskSupported"]
    assert "Client.GetProductVersion" in body
    assert "Major := 0;" in body
    assert "StrToIntDef(Copy(Ver, 1, Pos('.', Ver) - 1), 0)" in body
    assert "Result := Major >= 25;" in body
    assert "If Ver = '21.4.1.30' Then Result := True;" in body
    assert body.count("Result :=") == 2


def check_resolver(body):
    assert re.search(r"If Not PadCustomShapeSupported\(0\) Then Exit;\s+"
                     r"Result := S = eCustomShape;", body)


def test_independent_capabilities_live_in_early_shared_unit():
    check_capabilities(source("Utils.pas"))
    build = (ROOT / "build.py").read_text(encoding="utf-8")
    for name in FILES:
        assert build.index("'Utils.pas'") < build.index(repr(name))
    assert "LibraryAdvancedPadApiSupported" not in source("Library.pas")


def test_every_shape_resolver_is_guarded():
    utils = source("Utils.pas")
    assert len(re.findall(r"\beCustomShape\b", utils)) == 1
    check_resolver(functions(utils)["ShapeIsCustom"])
    counts = []
    for filename in FILES:
        text = source(filename)
        assert "eCustomShape" not in text
        counts.append(text.count("ShapeIsCustom("))
    assert counts == [4, 1, 2, 1], "update expected coverage when adding a reader"


def test_removing_the_shared_gate_is_detected():
    body = functions(source("Utils.pas"))["ShapeIsCustom"]
    broken = body.replace("If Not PadCustomShapeSupported(0) Then Exit;", "")
    assert broken != body
    with pytest.raises(AssertionError):
        check_resolver(broken)


@pytest.mark.parametrize("floor, changed", [
    ("AltiumVersionCode(0) >= 2208", "AltiumVersionCode(0) >= 2207"),
    ("Major >= 25", "Major >= 24"),
    ("Major >= 25", "Major >= 26"),
])
def test_changing_either_capability_floor_is_detected(floor, changed):
    text = source("Utils.pas")
    broken = text.replace(floor, changed)
    assert broken != text
    with pytest.raises(AssertionError):
        check_capabilities(broken)


def test_unknown_shape_is_not_reported_as_round():
    for filename in FILES:
        text = source(filename)
        uses = list(re.finditer(r"\bShapeIsCustom\(", text))
        assert uses
        for use in uses:
            # Restrict this check to the shape branch. The enclosing generic
            # getter also has legitimate round defaults for drill geometry.
            before = text[max(0, use.start() - 1200):use.start()]
            assert re.search(r"If (?:Pad\.TopShape|S) = eRounded Then", before)
            assert re.search(r"(?:ShapeStr|Str|Result|Name) := '(?:unknown|Unknown|Other)';", before)
            after = text[use.end():use.end() + 120]
            assert not re.search(r"Else (?:ShapeStr|Str|Result|Name) := '[Rr]ound';", after)


@pytest.mark.parametrize("replacement", ["21.4.1.29", "21.4.1.31", "21.4", "21", ""])
def test_changing_exact_mask_exception_is_detected(replacement):
    text = source("Utils.pas")
    broken = text.replace("Ver = '21.4.1.30'", "Ver = '" + replacement + "'")
    assert broken != text
    with pytest.raises(AssertionError):
        check_capabilities(broken)


def test_removing_exact_mask_exception_is_detected():
    text = source("Utils.pas")
    broken = text.replace("If Ver = '21.4.1.30' Then Result := True;", "")
    with pytest.raises(AssertionError):
        check_capabilities(broken)
