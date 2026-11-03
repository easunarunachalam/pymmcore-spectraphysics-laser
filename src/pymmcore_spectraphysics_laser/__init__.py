"""Spectra-Physics InSight / DeepSee laser for pymmcore-plus / napari-micromanager.

* :class:`LaserController` - the serial (pyvisa) interface to the laser.
* :class:`SpectraPhysicsLaser` - a pure-Python Micro-Manager device exposing
  the wavelength as a settable property (so it can live in channel presets)
  and reporting *busy* while retuning.  The serial port and the per-channel
  wavelengths are set in the Micro-Manager config file only (the package has
  no defaults for them)::

      #py pyDevice,Laser,pymmcore_spectraphysics_laser,SpectraPhysicsLaser
      #py Property,Laser,Port,ASRL<N>::INSTR
      #py ConfigGroup,channel,<preset>,Laser,Wavelength,<nm>

* :class:`LaserControlWidget` - the Qt control panel
  (``Plugins > Spectra-Physics Laser > Laser Control`` in napari).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._compat import apply_workarounds
from ._device import SpectraPhysicsLaser, locked_laser_controller
from .controller import LaserController
from .status_codes import state_defs, state_number

__version__ = "0.1.0"

__all__ = [
    "LaserControlWidget",
    "LaserController",
    "SpectraPhysicsLaser",
    "apply_workarounds",
    "locked_laser_controller",
    "state_defs",
    "state_number",
    "__version__",
]

# Preset handling with Python devices needs two small runtime fixes in the
# pymmcore-widgets preset dropdown (see _compat.py).  Applying them here means
# that loading a config file that references this module is enough; no
# launcher code.  PYMMCORE_PYDEVICE_NO_WORKAROUNDS=1 disables this.
apply_workarounds()

if TYPE_CHECKING:
    from ._widget import LaserControlWidget


def __getattr__(name: str):  # lazy: the widget pulls in Qt
    if name == "LaserControlWidget":
        from ._widget import LaserControlWidget

        return LaserControlWidget
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
