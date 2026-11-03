"""pytest configuration: the laser is simulated (pytest-qt provides ``qtbot``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pymmcore_spectraphysics_laser import LaserController
from pymmcore_spectraphysics_laser.fake_device import FakeDevice

# Test-only values (no real setup is described here).  Only #py lines: no C++
# devices, so no Micro-Manager device adapters are needed.  The simulator
# starts at 800 nm.
TEST_PORT = "ASRL1::INSTR"
PRESETS = {"ChanA": 800, "ChanB": 900, "ChanC": 1000}

TEST_CFG = f"""\
Property,Core,Initialize,0

#py pyDevice,Laser,pymmcore_spectraphysics_laser,SpectraPhysicsLaser
#py Property,Laser,Port,{TEST_PORT}
#py Property,Laser,Simulate,Yes

Property,Core,Initialize,1

#py Property,Laser,SettleTimeS,0.3

#py ConfigGroup,channel,ChanA,Laser,Wavelength,{PRESETS["ChanA"]}
#py ConfigGroup,channel,ChanB,Laser,Wavelength,{PRESETS["ChanB"]}
#py ConfigGroup,channel,ChanC,Laser,Wavelength,{PRESETS["ChanC"]}

Property,Core,ChannelGroup,channel
"""


@pytest.fixture
def fake_laser():
    """Fresh simulated laser per test (the controller is a process-wide singleton)."""
    LaserController.reset_instance()
    FakeDevice.retune_time_s = 0.2
    yield
    LaserController.reset_instance()
    FakeDevice.retune_time_s = 0.0


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.cfg"
    p.write_text(TEST_CFG)
    return p


@pytest.fixture
def core(fake_laser, cfg_path):
    from pymmcore_plus.experimental.unicore import UniMMCore

    mmc = UniMMCore()
    mmc.setTimeoutMs(20_000)
    mmc.loadSystemConfiguration(str(cfg_path))
    yield mmc
    mmc.unloadAllDevices()
