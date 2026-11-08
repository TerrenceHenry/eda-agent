# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Offline compatibility guards; native SDK binding still needs Altium tests."""
from pathlib import Path
import re
import pytest
from tests.pascal_source import functions, strip_comments

ROOT = Path(__file__).resolve().parents[1] / "scripts/altium"
MEMBER = re.compile(r"\.(SolderMaskBottomExpansion|UseSeparateExpansions|SolderMaskExpansionFromHoleEdge)\b")
# Inventory is intentional: new readers/writers must choose a safe capability path.
INVENTORY = {
    "Library.pas": {"Lib_SetViaProperties": (11, 12), "MaskBottomMM": (1, 1),
        "MaskSeparate": (1, 1), "Lib_GetPadGeometry": (3, 3),
        "Lib_SetPadProperties": (7, 8), "LibViaDetailJson": (1, 1)},
    "PCBGeneric.pas": {"PCBGetMask": (3, 1), "PCBSetMask": (3, 1)},
    "PCB.pas": {"PCB_GetPadProperties": (2, 2),
        "PCB_SetViaSoldermaskRelief": (4, 1), "LmMaskJson": (3, 2)},
}

def source(name):
    return strip_comments((ROOT / name).read_text(encoding="utf-8"))

def check_inventory(filename, text):
    bodies = functions(text)
    found = {name: (len(MEMBER.findall(body)), body.count("PadAdvancedMaskSupported(0)"))
             for name, body in bodies.items() if MEMBER.search(body)}
    assert found == INVENTORY[filename]
    for name in found:
        body = bodies[name]
        assert body.index("PadAdvancedMaskSupported(0)") < MEMBER.search(body).start()
        assert not re.search(r"PadAdvancedMaskSupported\(0\)\s+(?:And|Or)", body)

@pytest.mark.parametrize("filename", INVENTORY)
def test_all_advanced_member_paths_are_guarded(filename):
    check_inventory(filename, source(filename))

@pytest.mark.parametrize("filename", INVENTORY)
def test_removing_each_version_gate_is_detected(filename):
    text = source(filename)
    gates = list(re.finditer(r"PadAdvancedMaskSupported\(0\)", text))
    assert gates
    covered = 0
    for gate in gates:
        broken = text[:gate.start()] + "True" + text[gate.end():]
        # Entry checks outside a member-containing routine have separate tests.
        try:
            check_inventory(filename, broken)
        except AssertionError:
            covered += 1
    assert covered == sum(count for _, count in INVENTORY[filename].values())

@pytest.mark.parametrize("name", ["Lib_SetViaProperties", "Lib_SetPadProperties"])
def test_library_rejects_explicit_advanced_requests_before_mutation(name):
    body = functions(source("Library.pas"))[name]
    pre = body[:body.index("PcbBeginEdit(0)")]
    assert "If Not PadAdvancedMaskSupported(0) Then" in pre
    assert "'UNSUPPORTED_VERSION'" in pre
    for key in ("mask_bottom_expansion", "mask_separate", "mask_from_hole_edge"):
        assert "ExtractJsonValue(Params, '" + key + "') <> ''" in pre
    assert pre.index("'UNSUPPORTED_VERSION'") < pre.index("Exit;")


def test_generic_rejects_mixed_set_before_walk():
    text = source("PCBGeneric.pas")
    pre = text[text.index("If SetStr <> '' Then", text.index("Function UnresolvedLayerAssignment")):]
    pre = pre[:pre.index("JsonItems := ProcessPCBBoardObjects")]
    assert "If Not PadAdvancedMaskSupported(0) Then" in pre
    assert "If PCBSetNeedsAdvancedMask(SetStr) Then" in pre
    assert "Pos('SolderMask" not in pre
    assert "'UNSUPPORTED_VERSION'" in pre
    assert "Exit;" in pre


def test_legacy_top_values_remain_available_and_unknown_reads_are_null():
    bodies = functions(source("Library.pas"))
    for name in ("MaskBottomMM", "MaskSeparate"):
        assert "Result := 'null';" in bodies[name]
        assert "If Not PadAdvancedMaskSupported(0) Then Exit;" in bodies[name]
    for name in ("Lib_SetViaProperties", "Lib_SetPadProperties"):
        pre = bodies[name].split("'UNSUPPORTED_VERSION'", 1)[0]
        assert "ExtractJsonValue(Params, 'mask_expansion')" not in pre
    for name in ("PCBGetMask", "PCBSetMask"):
        body = functions(source("PCBGeneric.pas"))[name]
        assert "PropName = 'SolderMaskExpansion'" not in body[:body.index("Exit;")]


def test_via_writes_use_ad25_verified_typed_interface():
    library = functions(source("Library.pas"))["Lib_SetViaProperties"]
    assert "FoundPad := Found;" in library
    assert "MaskPrim := FoundPad;" in library
    assert "MaskPrim.SolderMaskExpansionFromHoleEdge :=" in library
    pcb = functions(source("PCB.pas"))["PCB_SetViaSoldermaskRelief"]
    assert "MaskPad := Via;" in pcb
    assert "MaskPrim := MaskPad;" in pcb
    assert "MaskPrim.SolderMaskExpansionFromHoleEdge :=" in pcb
    assert pcb.index("'UNSUPPORTED_VERSION'") < pcb.index("PcbBeginEdit(0)")


def test_preflight_parses_the_same_exact_keys_as_the_setter():
    bodies = functions(source("PCBGeneric.pas"))
    helper = bodies["PCBSetNeedsAdvancedMask"]
    setter = bodies["ApplySetPropertiesPCB"]
    # Require the production parser, not a substring approximation. Values
    # after the first equals sign never participate in the name comparison.
    start = "Remaining := SetStr;"
    end = "PropName := Copy(Assignment, 1, EqPos - 1);"
    def parser(body):
        return re.sub(r"\s+", " ", body[body.index(start):body.index(end) + len(end)])
    assert parser(helper) == parser(setter)
    keys = re.findall(r"PropName = '([^']+)'", helper)
    assert keys == ["SolderMaskBottomExpansion", "SolderMaskSeparate", "SolderMaskFromHoleEdge"]
    assert "Result := False;" in helper
    assert "Result := True;" in helper
    assert helper.count("Pos(") == 2


def test_pascal_exact_key_preflight_behavior(tmp_path):
    # Compile the actual extracted function when FPC is installed. No Altium
    # API or board is needed. Source-contract coverage above always runs.
    import shutil
    import subprocess
    compiler = shutil.which("fpc")
    if not compiler:
        pytest.skip("Free Pascal is not installed; exact parser source contract still checked")
    cases = [("Text=SolderMaskSeparate=true", False),
             ("Text=SolderMaskBottomExpansion=3", False),
             ("Text=SolderMaskFromHoleEdge=false", False),
             ("Text=x|SolderMaskSeparate=false", True),
             ("SolderMaskBottomExpansion=0|Text=x", True),
             ("SolderMaskFromHoleEdge=false", True),
             ("SolderMaskSeparate", False),
             ("Text=a=b|SolderMaskExpansion=3", False),
             ("|SolderMaskSeparate=|", True), ("", False)]
    helper = functions(source("PCBGeneric.pas"))["PCBSetNeedsAdvancedMask"]
    program = "program maskkeys;\n{$mode delphi}\n" + helper + "\nbegin\n"
    for value, _ in cases:
        program += "WriteLn(Ord(PCBSetNeedsAdvancedMask('" + value + "')));\n"
    program += "end.\n"
    path = tmp_path / "maskkeys.pas"
    path.write_text(program, encoding="utf-8")
    subprocess.run([compiler, str(path)], cwd=tmp_path, check=True, capture_output=True, text=True)
    exe = tmp_path / ("maskkeys.exe" if __import__("os").name == "nt" else "maskkeys")
    result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    assert [int(x) for x in result.stdout.splitlines()] == [int(want) for _, want in cases]


def test_layout_bottom_is_unknown_until_capability_has_been_checked():
    body = functions(source("PCB.pas"))["LmMaskJson"]
    known = body.index("Bottom := Cache.SolderMaskExpansion;")
    guard = body.rindex("If PadAdvancedMaskSupported(0) Then", 0, known)
    assert "Manual := '[' + IntToStr(Cache.SolderMaskExpansion) + ',null]';" in body[:guard]
    assert re.search(r"If PadAdvancedMaskSupported\(0\) Then\s+Begin\s+Bottom :=", body)
