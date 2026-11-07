# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 George Saliba <george.saliba@salitronic.com>
"""Fork-only policies, runnable with the standard library and no live EDA.

Keep these separate from upstream's tests: restoring an upstream test file
must not remove the checks that protect this fork's preferences.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Test this checkout even without an editable install (CI uses python -S).
sys.path.insert(0, str(ROOT / "src"))
from eda_agent import updates


class TestForkPolicies(unittest.TestCase):
    def bridge_sources(self):
        folder = ROOT / "scripts" / "altium"
        for name in ("StatusForm.pas", "StatusForm.dfm"):
            self.assertTrue((folder / name).is_file(), f"Missing {name}")
        paths = sorted(p for p in folder.iterdir()
                       if p.suffix.lower() in (".pas", ".dfm"))
        self.assertTrue(paths, "No bridge sources were checked")
        return [(p.name, p.read_text(encoding="utf-8-sig")) for p in paths]

    def test_no_sponsorship_banner_or_handlers(self):
        for name, text in self.bridge_sources():
            with self.subTest(source=name):
                self.assertNotRegex(
                    text, re.compile(r"sponsor|finding\s+eda.agent\s+useful", re.I),
                    "Sponsorship UI or handlers were restored")

    def test_no_heart_icons_even_if_the_control_is_renamed(self):
        # The removed Segoe MDL2 icon was U+E00B, written as #57355 in DFM.
        # Include literal hearts and Pascal's decimal/hex character escapes.
        hearts = (0xE00B, 0x2661, 0x2665, 0x2764, *range(0x1F493, 0x1F4A0),
                  0x1F5A4, 0x1F90D, 0x1F90E, 0x1F9E1, 0x1FA75, 0x1FA76, 0x1FA77)
        for name, text in self.bridge_sources():
            with self.subTest(source=name):
                for codepoint in hearts:
                    pattern = (re.escape(chr(codepoint))
                               + rf"|#{codepoint}\b|#\${codepoint:x}\b")
                    self.assertNotRegex(text, re.compile(pattern, re.I),
                                        "A heart icon was restored")

    def test_background_checks_require_explicit_opt_in(self):
        self.assertEqual(Path(updates.__file__).resolve(),
                         ROOT / "src" / "eda_agent" / "updates.py")
        for value in (None, "0", "false", "no", "off", "", "unexpected"):
            with self.subTest(update_check=value), patch.dict(os.environ):
                if value is None:
                    os.environ.pop("EDA_AGENT_UPDATE_CHECK", None)
                else:
                    os.environ["EDA_AGENT_UPDATE_CHECK"] = value
                self.assertFalse(updates._checks_enabled(),
                                 "Background checks must default to disabled")
                # Fail before any real thread, git command or network request.
                # Calling the public startup hook also catches removal of its
                # gate even if _checks_enabled() still returns False.
                with patch.object(updates.threading, "Thread",
                                  side_effect=AssertionError("Updater thread started")), \
                     patch.object(updates, "check",
                                  side_effect=AssertionError("Automatic check ran")), \
                     patch.object(updates.subprocess, "Popen",
                                  side_effect=AssertionError("Updater spawned a process")), \
                     patch.object(updates.urllib.request, "urlopen",
                                  side_effect=AssertionError("Updater contacted the network")):
                    updates.start_background_check()


if __name__ == "__main__":
    unittest.main()
