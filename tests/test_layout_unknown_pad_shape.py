# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""An explicit native unknown must never become rectangular copper."""
import pytest
from eda_agent.layout import geom
from eda_agent.layout.drc import run_drc
from eda_agent.layout.read_altium import read_board
from tests.test_drc_verdict_slivers_and_placement_on_copper import _fake_altium


@pytest.mark.parametrize("shape", ["unknown", "Unknown", "UNKNOWN"])
def test_explicit_unknown_shape_is_not_geometry(shape):
    with pytest.raises(ValueError, match="native pad shape is unknown"):
        geom.pad_shape(0, 0, 10, 20, shape)


def test_native_unknown_survives_read_then_geometry_and_drc_refuse():
    raw = {"name": "1", "comp": "", "x": 100000, "y": 200000,
           "net": "A", "copper": [["TopLayer", "unknown", 100000, 200000, 0, 0, 0]],
           "tent": [False, False], "from_hole": False, "mask": None}
    board = read_board(_fake_altium([raw], []))
    pad = board.pads[0]
    assert pad.copper[0].shape == "unknown"
    assert (pad.copper[0].w, pad.copper[0].h) == (10, 20)
    with pytest.raises(ValueError, match="native pad shape is unknown"):
        pad.shape_on("TopLayer")
    with pytest.raises(ValueError, match="native pad shape is unknown"):
        run_drc(board)


@pytest.mark.parametrize("shape,kind", [
    ("round", "segment"), ("oval", "segment"), ("roundrect", "poly"),
    ("octagon", "poly"), ("rect", "poly"), ("rectangular", "poly"),
])
def test_known_shape_behavior_is_unchanged(shape, kind):
    result = geom.pad_shape(0, 0, 10, 20, shape)
    assert result.kind == kind
    assert result.bbox == pytest.approx((-5, -10, 5, 10))
