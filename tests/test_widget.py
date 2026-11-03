"""LaserControlWidget with the simulated laser (pytest-qt)."""

from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from pymmcore_spectraphysics_laser import LaserControlWidget, LaserController, locked_laser_controller  # noqa: E402
from pymmcore_spectraphysics_laser._widget import NO_DEVICE_TEXT  # noqa: E402


def test_explicit_controller(qtbot, fake_laser):
    ctrl = locked_laser_controller(fake=True)
    w = LaserControlWidget(ctrl)
    qtbot.addWidget(w)
    assert w.read_status() == 50 and w.read_wavelength() == 800
    assert w.status_string.text() == "Running mode"
    assert w.laser_onoff_button.text() == "ON"

    w.wavelength_edit.setText("850")
    w.update_wavelength()
    qtbot.waitUntil(lambda: LaserController.instance(fake=True).get_wavelength() == 850, timeout=2000)

    w.on_pump_shutter_button_clicked()
    w.update_internal_status()
    assert w.pump_shutter_button.text() == "OPEN"


def test_discovers_device_in_core(qtbot, core):
    w = LaserControlWidget(mmcore=core)
    qtbot.addWidget(w)
    assert w.laser_controller is not None
    assert w.laser_controller._target is LaserController.instance(fake=True)
    assert w.read_wavelength() == 800


def test_waits_for_device_then_attaches(qtbot, fake_laser, cfg_path):
    from pymmcore_plus.experimental.unicore import UniMMCore

    mmc = UniMMCore()
    mmc.setTimeoutMs(20_000)
    w = LaserControlWidget(mmcore=mmc)
    qtbot.addWidget(w)
    assert w.laser_controller is None and w.status_string.text() == NO_DEVICE_TEXT

    mmc.loadSystemConfiguration(str(cfg_path))  # systemConfigurationLoaded -> attach
    qtbot.waitUntil(lambda: w.laser_controller is not None, timeout=3000)
    assert w.read_wavelength() == 800
    mmc.unloadAllDevices()


def test_plugin_construction_without_arguments(qtbot, monkeypatch, core):
    """napari constructs the widget with no arguments: it must find the core itself."""
    import pymmcore_spectraphysics_laser._widget as wmod

    monkeypatch.setattr(wmod, "find_core", lambda explicit=None: core)
    w = LaserControlWidget()
    qtbot.addWidget(w)
    assert w.laser_controller is not None and w.core is core
