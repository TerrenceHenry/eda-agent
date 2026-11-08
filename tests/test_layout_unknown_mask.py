# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Unknown native mask fields cannot turn into a clear layout verdict."""
import pytest
from eda_agent.layout.drc import mask_openings, mask_slivers, usual_via_mask
from eda_agent.layout.read_altium import read_board
from eda_agent.layout.rules import RuleSet
from tests.test_drc_verdict_slivers_and_placement_on_copper import _fake_altium, _via

@pytest.mark.parametrize("unknown", [
    {"from_hole": None, "mask": [10000, 20000]},
    {"from_hole": False, "mask": [10000, None]},
    {"from_hole": None, "mask": [10000, None]},
    {"from_hole": None, "mask": None},
])
def test_unknown_mask_is_preserved_and_no_sliver_verdict_is_claimed(unknown):
    b = read_board(_fake_altium([], [_via(tent=[False, False], **unknown)]))
    via = b.vias[0]
    assert via.mask_from_hole is unknown["from_hole"]
    assert via.mask_manual == (None if unknown["mask"] is None else
                              [None if v is None else v / 10000 for v in unknown["mask"]])
    assert b.meta["mask_read"] is False
    assert "unavailable" in b.meta["mask_unavailable_reason"]
    assert mask_slivers(b) is None
    assert usual_via_mask(b) is None
    with pytest.raises(ValueError, match="unavailable mask fields"):
        mask_openings(b, RuleSet.from_board(b))


def test_one_complete_object_does_not_hide_an_unread_object():
    b = read_board(_fake_altium([], [
        _via(tent=[False, False], from_hole=False, mask=[10000, 20000]),
        _via()]))
    assert b.meta["mask_read"] is False
    assert b.vias[1].mask_from_hole is None
    assert mask_slivers(b) is None
    assert usual_via_mask(b) is None


@pytest.mark.parametrize("manual", [None, [10000, 20000], [0, 0]])
def test_complete_mask_stays_usable_including_rule_driven_values(manual):
    b = read_board(_fake_altium([], [_via(tent=[False, False], from_hole=False, mask=manual)]))
    assert b.meta["mask_read"] is True
    assert mask_slivers(b) == []
    assert usual_via_mask(b) is not None
    assert len(mask_openings(b, RuleSet.from_board(b))) == 2



def test_unknown_pad_cannot_be_hidden_by_a_complete_via():
    pad = {"name": "1", "comp": "U1", "x": 0, "y": 0, "copper": [],
           "tent": [False, False], "from_hole": None, "mask": [10000, None]}
    b = read_board(_fake_altium([pad], [
        _via(tent=[False, False], from_hole=False, mask=None)]))
    assert b.pads[0].mask_from_hole is None
    assert b.pads[0].mask_manual == [1.0, None]
    assert b.meta["mask_read"] is False
    assert mask_slivers(b) is None
    assert usual_via_mask(b) is None


@pytest.mark.parametrize("unknown", [
    {"from_hole": None, "mask": None},
    {"from_hole": False, "mask": [10000, None]},
])
def test_native_unknown_audit_explains_api_limit_not_redeployment(unknown):
    from eda_agent.layout.audit import drc_summary
    from tests.test_drc_verdict_slivers_and_placement_on_copper import SLIVER
    board = read_board(_fake_altium([], [_via(tent=[False, False], **unknown)]))
    board.rules = [SLIVER]
    result = drc_summary(board)
    assert result["pass"] is False
    assert result["status"] == "incomplete"
    note = " ".join(result["notes"])
    assert board.meta["mask_unavailable_reason"] in note
    assert "Altium version/API" in note
    assert "native Altium DRC" in note
    assert "deploy" not in note


def test_old_script_without_mask_fields_keeps_redeployment_advice():
    from eda_agent.layout.audit import drc_summary
    from tests.test_drc_verdict_slivers_and_placement_on_copper import SLIVER
    board = read_board(_fake_altium([], [_via()]))
    board.rules = [SLIVER]
    assert "mask_unavailable_reason" not in board.meta
    result = drc_summary(board)
    assert result["status"] == "incomplete"
    assert any("deploy the current scripts and read it again" in note for note in result["notes"])
