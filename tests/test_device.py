"""SpectraPhysicsLaser loaded from a config file into a UniMMCore (simulated laser)."""

from __future__ import annotations

import time

import pytest

from conftest import PRESETS, TEST_PORT
from pymmcore_spectraphysics_laser import LaserController, SpectraPhysicsLaser, locked_laser_controller


def test_load_and_properties(core):
    assert "Laser" in core.getLoadedDevices()
    assert core.getDeviceName("Laser") == "SpectraPhysicsLaser"
    assert core.getProperty("Laser", "Port") == TEST_PORT
    assert core.getProperty("Laser", "Simulate") == "Yes"
    assert core.getProperty("Laser", "Wavelength") == "800"
    assert core.getProperty("Laser", "SettleTimeS") == "0.3"
    assert core.getProperty("Laser", "Status") == "50"
    assert float(core.getProperty("Laser", "Power")) > 0
    assert not core.deviceBusy("Laser")
    assert core.getChannelGroup() == "channel"


def test_port_must_come_from_the_config(fake_laser):
    """No port in the config and not simulating: initialisation fails with a clear message."""
    from pymmcore_plus import DeviceInitializationState
    from pymmcore_plus.experimental.unicore import UniMMCore

    mmc = UniMMCore()
    dev = SpectraPhysicsLaser()
    assert dev.get_property_value("Port") == ""  # no built-in default
    mmc.loadPyDevice("Laser", dev)
    mmc.initializeDevice("Laser")  # UniMMCore records the error instead of raising
    assert mmc.getDeviceInitializationState("Laser") != DeviceInitializationState.InitializedSuccessfully
    assert "Port" in str(dev._initialized_) and "config" in str(dev._initialized_)
    mmc.unloadAllDevices()


def test_preset_retune_busy_and_settle(core):
    laser = LaserController.instance(fake=True)
    core.setConfig("channel", "ChanB")
    assert core.deviceBusy("Laser")
    t0 = time.perf_counter()
    core.waitForSystem()
    dt = time.perf_counter() - t0
    assert dt >= 0.2 + 0.3 - 0.05  # retune + settle
    assert laser.get_wavelength() == PRESETS["ChanB"]
    assert core.getProperty("Laser", "Wavelength") == str(PRESETS["ChanB"])  # exact preset text
    assert core.getCurrentConfig("channel") == "ChanB"
    assert core.getCurrentConfigFromCache("channel") == "ChanB"


def test_same_wavelength_does_not_retune(core):
    laser = LaserController.instance(fake=True)
    n = len([c for c in laser.device.log if c.lower().startswith("wav ")])
    core.setConfig("channel", "ChanA")  # already at 800
    assert len([c for c in laser.device.log if c.lower().startswith("wav ")]) == n
    assert not core.deviceBusy("Laser")


def test_out_of_range_rejected(core):
    with pytest.raises(Exception):
        core.setProperty("Laser", "Wavelength", 100)
    with pytest.raises(Exception):
        core.setProperty("Laser", "SettleTimeS", -1)


def test_shared_connection(core):
    """The widget-side helper returns the very same connection as the device."""
    proxy = locked_laser_controller(TEST_PORT, fake=True)
    assert proxy._target is LaserController.instance(fake=True)
    core.setConfig("channel", "ChanC")
    core.waitForSystem()
    assert proxy.get_wavelength() == PRESETS["ChanC"]


def test_config_roundtrip(core, tmp_path):
    out = tmp_path / "saved.cfg"
    core.saveSystemConfiguration(str(out))
    text = out.read_text()
    assert "#py pyDevice,Laser,pymmcore_spectraphysics_laser,SpectraPhysicsLaser" in text
    assert f"#py Property,Laser,Port,{TEST_PORT}" in text
    assert "#py Property,Laser,Simulate,Yes" in text
    assert f"#py ConfigGroup,channel,ChanB,Laser,Wavelength,{PRESETS['ChanB']}" in text


def test_shutdown_keeps_laser_running(core):
    laser = LaserController.instance(fake=True)
    core.unloadAllDevices()
    assert laser.get_status() == 50 and not laser.device.closed
