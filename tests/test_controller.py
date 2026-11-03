"""LaserController against the simulated laser."""

from __future__ import annotations

import time

import pytest

from pymmcore_spectraphysics_laser import LaserController, state_defs, state_number


def test_port_is_required_for_hardware(fake_laser):
    with pytest.raises(ValueError, match="Port"):
        LaserController(port_name=None)
    with pytest.raises(ValueError, match="Port"):
        LaserController.instance()  # no port, not fake


def test_singleton_and_basic_readings(fake_laser):
    a = LaserController.instance(fake=True)
    b = LaserController.instance(port_name="ignored", fake=True)
    assert a is b
    assert a.min_wavelength == 680 and a.max_wavelength == 1300
    assert a.get_status() == 50 and state_defs(a.get_status_word()) == "Running"
    assert a.get_wavelength() == 800
    assert a.get_power() > 0 and a.get_mode() == "RUN"
    assert a.get_watchdog_time() == 0.0


def test_wavelength_range_and_retune(fake_laser):
    laser = LaserController.instance(fake=True)
    with pytest.raises(ValueError):
        laser.set_wavelength(100)
    laser.set_wavelength(900)
    assert laser.get_wavelength() == 800  # still retuning
    time.sleep(0.25)
    assert laser.get_wavelength() == 900


def test_shutters_modes_power(fake_laser):
    laser = LaserController.instance(fake=True)
    assert not laser.pump_shutter_state() and not laser.IR_shutter_state()
    laser.open_pump_shutter()
    laser.open_IR_shutter()
    assert laser.pump_shutter_state() and laser.IR_shutter_state()
    laser.close_pump_shutter()
    assert not laser.pump_shutter_state()

    laser.set_mode_align()
    assert laser.get_status() == 60 and laser.get_mode() == "ALIGN"
    laser.set_mode_run()
    assert laser.get_status() == 50

    laser.power_off()
    assert laser.get_status() == 25
    laser.power_on(blocking=False)
    assert laser.get_status() == 50
    with pytest.raises(ValueError):
        laser.power_on()  # already on: not in the "ready" state

    laser.close()
    assert laser.device.closed and laser.get_watchdog_time() == 3.0


def test_state_number():
    assert state_number(50 << 16) == 50
    assert state_number(str((25 << 16) | 0b1111)) == 25
