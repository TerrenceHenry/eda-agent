# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Guard the unsupported AD21 members and the live-iterator mutation.

Native mutation checks belong on disposable documents only. These guards
also mutate the recorded defects back into the source in memory, so an
assertion which cannot detect its target defect cannot pass unnoticed.
"""
from pathlib import Path
import re

import pytest

from eda_agent.bridge.exceptions import AltiumCommandError
from eda_agent.tools import pcb
from tests.pascal_source import load

ROOT = Path(__file__).resolve().parents[1]


def _pcb():
    return load(ROOT / "scripts/altium/PCB.pas")


def _safe_placement(body):
    assert not re.search(r"\bBody\.[xy]\b", body, re.I)
    assert "BeforeBox := Body.BoundingRectangle" in body
    assert "AfterBox := Body.BoundingRectangle" in body
    assert "JsonBool('position_verified', PositionOk)" in body
    assert "Abs(ReadBackX - BodyX)" in body
    assert "Abs(ReadBackY - BodyY)" in body


def test_body_placement_never_probes_the_missing_xy_members():
    body = _pcb()["PCB_Place3DBody"]
    _safe_placement(body)
    with pytest.raises(AssertionError):
        _safe_placement(body.replace("BeforeBox := Body.BoundingRectangle;",
                                     "CurX := Body.x;"))
    generic = load(ROOT / "scripts/altium/PCBGeneric.pas")["PCBPrimitivePos"]
    assert not re.search(r"\bBody\.[xy]\b", generic, re.I)


def test_step_standoff_is_set_on_model_before_binding():
    body = _pcb()["PCB_Place3DBody"]
    assert "Body.StandoffHeight :=" not in body
    assert body.index("Model.SetState(0, 0, 0, MilsToCoordF(Standoff))") < body.index("Body.Model := Model")
    move = body.index("Body.MoveByXY(MilsToCoordF(BodyX)")
    assert body.index("Board.AddPCBObject(Body)") < body.index("Body.BeginModify") < move
    assert move < body.index("Body.EndModify") < body.index("PcbEndEdit(0)")


def _safe_visibility(body):
    destroyed = body.index("Board.BoardIterator_Destroy(Iter)")
    for member in ("NameOn", "CommentOn"):
        writes = list(re.finditer(rf"Comp\.{member}\s*:=", body))
        assert writes
        for write in writes:
            assert write.start() > destroyed
            assert body.rindex("Comp.BeginModify", 0, write.start()) > destroyed
            assert body.index("Comp.EndModify", write.end()) > write.end()


def test_visibility_writes_only_after_destroying_iterator_and_verifies_result():
    body = _pcb()["PCB_SetTextVisibility"]
    _safe_visibility(body)
    with pytest.raises(AssertionError):
        _safe_visibility(body.replace("Comps.Add(Comp);", "Comp.NameOn := NamesOn;"))
    assert "If Comp.NameOn = NamesOn Then" in body
    assert "If Comp.CommentOn = CommentsOn Then" in body
    assert "JsonInt('failed', Failed)" in body and "Comps.Free" not in body


def test_ad21_visibility_is_refused_before_touching_board_or_starting_edit():
    body = _pcb()["PCB_SetTextVisibility"]
    guard = body.index("If Major < 22 Then")
    refusal = body.index("'UNSUPPORTED'", guard)
    assert body.index("Client.GetProductVersion") < guard
    assert refusal < body.index("GetPCBBoardAnywhere")
    assert refusal < body.index("TInterfaceList.Create") < body.index("PcbBeginEdit(0)")


@pytest.mark.parametrize("routine", ["PCB_LayerStackManager", "PCB_MoveLayer", "PCB_LoadStackManagerModel"])
def test_stack_sdk_is_rejected_before_any_late_bound_call(routine):
    body = _pcb()[routine]
    gate = body.index("Problem := PCBStackManagerProblem(0)")
    assert gate < body.index("LSM := LayerStackManager")
    assert "'UNSUPPORTED'" in body[gate:body.index("LSM := LayerStackManager")]
    assert not re.search(r"ApplyToPcb|\.SetState_|MarkDocDirty", body[:gate])
    helper = _pcb()["PCBStackManagerProblem"]
    assert "Client.GetProductVersion" in helper and "If Major < 25 Then" in helper


@pytest.mark.asyncio
async def test_optional_sync_skips_only_unsupported_sdk_without_sending_mutation():
    class Bridge:
        def __init__(self, code):
            self.code = code
            self.sent = []

        async def send_command_async(self, command, params=None):
            self.sent.append(command)
            raise AltiumCommandError("SDK unavailable", code=self.code)

    bridge = Bridge("UNSUPPORTED")
    assert await pcb.sync_stack_manager(bridge) == {
        "supported": False, "skipped": True, "reason": "SDK unavailable"}
    assert bridge.sent == ["pcb.layer_stack_manager"]
    with pytest.raises(AltiumCommandError):
        await pcb.sync_stack_manager(Bridge("INTERNAL_ERROR"))
