"""The preset-dropdown workarounds: selecting a preset must never apply a different one."""

from __future__ import annotations

import pytest

from conftest import PRESETS
from pymmcore_spectraphysics_laser import LaserController, _compat, apply_workarounds

pytest.importorskip("pymmcore_widgets")

from pymmcore_widgets import PresetsWidget  # noqa: E402


def _retunes(laser) -> int:
    return len([c for c in laser.device.log if c.lower().startswith("wav ")])


def test_patched_and_idempotent():
    for name in ("_update_if_props_not_match_preset", "_on_cfg_set"):
        fn = PresetsWidget.__dict__[name]
        assert getattr(fn, _compat.MARK, False)
        apply_workarounds()
        assert PresetsWidget.__dict__[name] is fn


def test_selecting_a_preset_retunes_once_and_stays_selected(qtbot, core):
    laser = LaserController.instance(fake=True)
    pw = PresetsWidget("channel", mmcore=core)
    qtbot.addWidget(pw)
    assert pw.value() == "ChanA"

    core.setConfig("channel", "ChanB")  # some previous channel
    core.waitForSystem()
    qtbot.wait(50)
    assert pw.value() == "ChanB"

    n = _retunes(laser)
    pw.setValue("ChanC")  # user picks a preset in the dropdown -> setConfig
    # widget refreshes arriving while the laser is still retuning
    for _ in range(3):
        qtbot.wait(30)
        pw._on_property_changed("Laser", "Wavelength", str(PRESETS["ChanB"]))
    core.waitForSystem()
    pw._update_if_props_not_match_preset()
    qtbot.wait(50)

    assert _retunes(laser) == n + 1, "exactly one retune command"
    assert laser.get_wavelength() == PRESETS["ChanC"]
    assert pw.value() == "ChanC"
    assert core.getCurrentConfig("channel") == "ChanC"
