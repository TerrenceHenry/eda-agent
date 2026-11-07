# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Guards for the two library commands that halted Altium 21.4.1.

The screenshot identifies eCustomShape, not a corrupt footprint, in the
read-only pad query. Missing DelphiScript identifiers are not catchable.
The single-library export stopped at the one-call SDK exporter; the
replacement must copy to a fresh document without pruning the source.
Native scratch-library validation remains separate from these source checks.
"""
from pathlib import Path
import re

from tests.pascal_source import strip_comments


LIBRARY = Path(__file__).resolve().parents[1] / "scripts/altium/Library.pas"


def code():
    return strip_comments(LIBRARY.read_text(encoding="utf-8"))


def routine(name):
    text = code()
    start = text.index(f"Function {name}(")
    end = re.search(r"\n(?:Function|Procedure) ", text[start + 1:])
    return text[start:start + 1 + end.start()] if end else text[start:]


def test_custom_shape_never_resolves_on_ad21():
    gate = routine("LibraryAdvancedPadApiSupported")
    assert "Client.GetProductVersion" in gate
    assert "Result := Major >= 26;" in gate
    text = code()
    uses = list(re.finditer(r"Pad\.TopShape = eCustomShape", text))
    assert len(uses) == 4
    for use in uses:
        assert re.search(
            r"Else If LibraryAdvancedPadApiSupported\(0\) Then\s+If $",
            text[max(0, use.start() - 130):use.start()])


def test_pad_read_uses_typed_cache_and_marks_unmeasured_fields_unavailable():
    body = routine("Lib_GetPadGeometry")
    assert "Pad.Cache." not in body
    assert "PadCache := Pad.GetState_Cache;" in body
    assert "ExpBottomJson := 'null';" in body
    assert "ExpSeparateJson := 'null';" in body
    assert re.search(r"If LibraryAdvancedPadApiSupported\(0\) Then\s+Begin\s+"
                     r"ExpSeparate := PadCache.UseSeparateExpansions", body)
    assert re.search(r"If LibraryAdvancedPadApiSupported\(0\) Then\s+Begin\s+"
                     r"ExpBottom := CoordToMM\(PadCache.SolderMaskBottomExpansion\)", body)
    assert "Pad.Cache." not in routine("CacheStateName")
    assert "Cache := Pad.GetState_Cache;" in routine("CacheStateName")


def test_export_uses_a_new_destination_and_never_the_crashing_sdk_method():
    body = routine("Lib_SaveFootprintLibrary")
    assert ".SaveComponentWithLibrary(" not in body
    create = body.index("Client.OpenNewDocument(")
    for guard in ("'SAME_LIBRARY'", "'ALREADY_OPEN'", "'OUTPUT_EXISTS'", "'INVALID_PATH'"):
        assert body.index(guard) < create
    assert body.index("SaveHeldBack(OutPath)") < create
    assert "OutDoc.SetFileName(OutPath);" in body
    assert body.index("PcbLibPathProblem(DestLib, OutPath)") < body.index("PcbBeginEdit(0)")
    assert "Footprint.CopyTo(NewFP, eFullCopy);" in body
    assert "AlignCopiedFootprint(Footprint, NewFP)" in body
    assert "DestLib.RegisterComponent(NewFP);" in body
    assert re.search(r"Finally\s+PcbEndEdit\(0\);", body)
    assert body.index("DestLib.ComponentCount <> 1") < body.index("OutDoc.DoFileSave('')")
    assert not re.search(r"\bPcbLib\.(?:RemoveComponent|DeRegisterComponent|Save)", body)
    assert "MarkDocDirtyByPath(OutPath);" in body
    assert "Said := FileExists(OutPath);" in body
    assert body.index("If Not Said Then") < body.index("ForgetDocEdited(OutPath)")
