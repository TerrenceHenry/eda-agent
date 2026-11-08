# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Prevent the native AD21 filtered-traversal regression; not an SDK emulator."""
from pathlib import Path
import re
import pytest
SOURCE = Path(__file__).resolve().parents[1] / 'scripts/altium/PCB.pas'

def loop(source):
    assert source.count('Function PCB_SetTextVisibility(') == 1
    body = source.split('Function PCB_SetTextVisibility(', 1)[1].split('\nEnd;', 1)[0]
    walk = body.split('While Obj <> Nil Do', 1)[1].split('Board.BoardIterator_Destroy(Iter)', 1)[0]
    return re.sub(r'\{.*?\}', '', walk, flags=re.S)

def assert_safe_walk(source):
    walk = loop(source)
    assert not re.search(r'\bContinue\s*;', walk, re.I)
    assert walk.count('Iter.NextPCBObject') == 1
    assert walk.index('Iter.NextPCBObject') > walk.index("Except NoteWriteFailed('NameOn/CommentOn'); End;")
    assert "If (Not HasFilter) Or (Pos(NameMark, '|' + FilterStr + '|') > 0) Then" in walk
    assert 'Comps.Add(Comp);' in walk

def test_filter_has_one_fallthrough_advance():
    assert_safe_walk(SOURCE.read_text())

def test_guard_rejects_restored_continue_mutation():
    source = SOURCE.read_text()
    needle = "                    If (Not HasFilter) Or (Pos(NameMark, '|' + FilterStr + '|') > 0) Then\n                        Comps.Add(Comp);"
    assert source.count(needle) == 1
    bad = source.replace(needle, "                    If HasFilter And (Pos(NameMark, '|' + FilterStr + '|') = 0) Then Begin\n                        Obj := Iter.NextPCBObject;\n                        Continue;\n                    End;\n                    Comps.Add(Comp);")
    with pytest.raises(AssertionError):
        assert_safe_walk(bad)

def test_unverified_older_host_containment_is_retained():
    source = SOURCE.read_text().split('Function PCB_SetTextVisibility(',1)[1].split('\nEnd;',1)[0]
    assert "If (Major < 22) And (Version <> '21.4.1.30') Then" in source
    assert source.index("If (Major < 22) And (Version <> '21.4.1.30') Then") < source.index('Comps := TInterfaceList.Create')


def assert_narrow_version_gate(source):
    body = source.split('Function PCB_SetTextVisibility(', 1)[1].split('\nEnd;', 1)[0]
    gate = "If (Major < 22) And (Version <> '21.4.1.30') Then"
    assert body.count(gate) == 1
    assert body.index(gate) < body.index('GetPCBBoardAnywhere')


def test_guard_exception_is_exact_and_mutation_sensitive():
    source = SOURCE.read_text()
    assert_narrow_version_gate(source)
    for bad in [source.replace("Version <> '21.4.1.30'", 'Major <> 21'),
                source.replace("Version <> '21.4.1.30'", "Version <> '21.4.1.31'")]:
        with pytest.raises(AssertionError):
            assert_narrow_version_gate(bad)


@pytest.mark.parametrize('version,blocked', [('', True), ('garbage', True),
    ('21', True), ('21.4.1.29', True), ('21.4.1.31', True), ('20.2.1.1', True),
    ('21.4.1.30', False), ('22.0.0.0', False), ('25.8.1.18', False)])
def test_documented_version_policy(version, blocked):
    # Policy model only; not a substitute for running those Altium versions.
    assert_narrow_version_gate(SOURCE.read_text())
    try:
        major = int(version.split('.', 1)[0])
    except ValueError:
        major = 0
    assert ((major < 22) and version != '21.4.1.30') is blocked
