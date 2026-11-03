"""
Spectra-Physics tunable laser as a Micro-Manager (pymmcore-plus UniMMCore)
Python generic device.

The wavelength is exposed as a settable property so that it can be part of a
channel preset.  Everything setup-specific (which serial port, which
wavelength per channel) is written in the Micro-Manager config file and
nowhere else; this package has no defaults for them::

    #py pyDevice,Laser,pymmcore_spectraphysics_laser,SpectraPhysicsLaser
    #py Property,Laser,Port,ASRL<N>::INSTR          (COM<N>)
    #py ConfigGroup,channel,<preset>,Laser,Wavelength,<nm>

``busy()`` reports True while the laser is retuning and for ``SettleTimeS``
seconds after the requested wavelength is reached, so the core's
``waitForSystem()`` (called by the MDA engine after applying a channel
preset) blocks until the laser is ready.

Pre-init properties
-------------------
Port
    pyvisa resource name of the laser's serial port, ``ASRL<N>::INSTR`` for
    COM<N>.  Required (no default) unless ``Simulate`` is ``Yes``.
Simulate
    ``Yes`` talks to the in-memory :class:`~.fake_device.FakeDevice` instead
    of hardware.

Runtime properties
------------------
Wavelength
    Pump wavelength in nm; settable.
SettleTimeS
    Extra seconds the device stays busy after reaching the wavelength
    (default 10).
Status, Power
    Read-only.

The serial connection is the process-wide :class:`LaserController` singleton
and is shared with :class:`LaserControlWidget`; *all* access goes through a
lock-protecting proxy from :func:`locked_laser_controller`.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pymmcore_plus.experimental.unicore import GenericDevice, pymm_property

from .controller import LaserController

DEFAULT_SETTLE_S = 10.0

_LASER_LOCK = threading.RLock()


class _LockedProxy:
    """Wrap an object so that every method call holds a shared re-entrant lock."""

    def __init__(self, target: Any, lock: threading.RLock) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_lock", lock)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        lock = self._lock

        def _locked(*args: Any, **kwargs: Any) -> Any:
            with lock:
                return attr(*args, **kwargs)

        return _locked

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, value)


def locked_laser_controller(port_name: str | None = None, fake: bool = False) -> Any:
    """The shared, lock-protected :class:`LaserController` singleton.

    The first call opens the connection on ``port_name`` (required unless
    ``fake``, which uses the simulator); later calls, from any module, return
    a proxy to the same controller.
    """
    return _LockedProxy(LaserController.instance(port_name=port_name, fake=fake), _LASER_LOCK)


class SpectraPhysicsLaser(GenericDevice):
    """Spectra-Physics tunable laser: wavelength as a preset-able property."""

    def __init__(self) -> None:
        super().__init__()
        self._port = ""  # no default: comes from the config file
        self._simulate = "No"
        self._settle_s = DEFAULT_SETTLE_S
        self._ctrl: Any = None
        self._target_wavelength: int | None = None
        # exact text the Wavelength property was last set with (see Wavelength)
        self._target_text: str | None = None
        self._reached_at: float | None = None

    # ------------------------------------------------------------------ pre-init
    # NOTE: all getters return str (like C++ device properties) because
    # pymmcore-widgets forwards getProperty() values into str-typed Qt signals.

    @pymm_property(is_pre_init=True, property_type=str)
    def Port(self) -> str:
        return self._port

    @Port.setter
    def Port(self, value: str) -> None:
        self._port = str(value).strip()

    @pymm_property(is_pre_init=True, allowed_values=["Yes", "No"], property_type=str)
    def Simulate(self) -> str:
        return self._simulate

    @Simulate.setter
    def Simulate(self, value: str) -> None:
        self._simulate = str(value)

    # ------------------------------------------------------------------ runtime

    @pymm_property(property_type=float)
    def SettleTimeS(self) -> str:
        """Seconds to stay 'busy' after the target wavelength is reached."""
        return f"{self._settle_s:g}"

    @SettleTimeS.setter
    def SettleTimeS(self, value: Any) -> None:
        settle = float(value)
        if not 0.0 <= settle <= 600.0:
            raise ValueError(f"{self.get_label()}: SettleTimeS {settle} out of range 0-600 s")
        self._settle_s = settle

    @pymm_property(property_type=int)
    def Wavelength(self) -> str:
        """Pump wavelength in nm (the controller enforces its own min/max).

        Once the laser is at the wavelength last set through this property,
        the exact text it was set with is returned (the preset widgets compare
        strings character by character); while retuning, the live wavelength.
        """
        if self._ctrl is None:
            return str(self._target_wavelength or 0)
        live = int(self._ctrl.get_wavelength())
        if live == self._target_wavelength and self._target_text is not None:
            return self._target_text
        return str(live)

    @Wavelength.setter
    def Wavelength(self, value: Any) -> None:
        # no `limits=` on the property so the original text reaches us intact
        ctrl = self._require_ctrl()
        text = str(value).strip()
        wav = int(round(float(text)))
        if self._target_wavelength == wav and int(ctrl.get_wavelength()) == wav:
            self._target_text = text
            return  # already there: don't restart the settle timer
        ctrl.set_wavelength(wav)  # raises ValueError outside the laser's range
        self._target_wavelength = wav
        self._target_text = text
        self._reached_at = None

    @pymm_property(is_read_only=True, property_type=int)
    def Status(self) -> str:
        return str(int(self._ctrl.get_status())) if self._ctrl is not None else "-1"

    @pymm_property(is_read_only=True, property_type=float)
    def Power(self) -> str:
        return f"{float(self._ctrl.get_power()):.3f}" if self._ctrl is not None else "0"

    # ------------------------------------------------------------------ lifecycle

    def initialize(self) -> None:
        simulate = self._simulate == "Yes"
        if not simulate and not self._port:
            raise ValueError(
                f"{self.get_label()}: the Port pre-init property is not set. Put the laser's "
                "serial port in the Micro-Manager config, e.g. "
                f"'#py Property,{self.get_label()},Port,ASRL<N>::INSTR' for COM<N>."
            )
        self._ctrl = locked_laser_controller(self._port or None, fake=simulate)
        self._target_wavelength = int(self._ctrl.get_wavelength())
        self._reached_at = time.monotonic() - self._settle_s  # start "ready"
        super().initialize()

    def shutdown(self) -> None:
        # Deliberately do NOT power the laser off or close the port: the
        # connection is shared with the control widget and outlives the
        # Micro-Manager session.
        self._ctrl = None
        super().shutdown()

    def _require_ctrl(self) -> Any:
        if self._ctrl is None:
            raise RuntimeError(f"{self.get_label()}: device not initialised")
        return self._ctrl

    # ------------------------------------------------------------------ busy

    def busy(self) -> bool:
        if self._ctrl is None or self._target_wavelength is None:
            return False
        if int(self._ctrl.get_wavelength()) != self._target_wavelength:
            self._reached_at = None
            return True
        now = time.monotonic()
        if self._reached_at is None:
            self._reached_at = now
        return (now - self._reached_at) < self._settle_s


# UniMMCore writes `pyDevice,<label>,<class.__module__>,<class name>` when a
# config is saved: use the public import path rather than this private module.
SpectraPhysicsLaser.__module__ = "pymmcore_spectraphysics_laser"
