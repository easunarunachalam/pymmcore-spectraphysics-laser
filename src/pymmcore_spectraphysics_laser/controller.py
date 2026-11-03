"""
Serial control of a Spectra-Physics InSight / DeepSee laser (pyvisa).

Derived from davy-jones by John Russell (MIT licence, see LICENSE-davy-jones).

Use :meth:`LaserController.instance` rather than the constructor so that the
laser's serial port is opened only once per process::

    laser = LaserController.instance(port_name="ASRL<N>::INSTR")   # COM<N>
    laser.set_wavelength(800)

There is no default port: it is a property of the setup and belongs in the
Micro-Manager config file (the ``Port`` pre-init property of the
:class:`~pymmcore_spectraphysics_laser.SpectraPhysicsLaser` device).

``instance(fake=True)`` talks to :class:`~.fake_device.FakeDevice` instead of
hardware and needs no port.
"""

from __future__ import annotations

import time
import warnings
from typing import Any

from .status_codes import BIT_IR_SHUTTER, BIT_MAIN_SHUTTER, state_number

__all__ = ["LaserController", "port_map"]


def port_map() -> None:
    """Print the serial ports that can be opened (helps to find the laser's)."""
    import serial
    from serial import SerialException
    from serial.tools import list_ports

    for p in list_ports.comports():
        try:
            s_test = serial.Serial(p.name)
            s_test.close()
            print(p)
        except SerialException:
            pass


_instance: LaserController | None = None


class LaserController:
    """Wrapper around the laser's serial command set."""

    @classmethod
    def instance(
        cls, port_name: str | None = None, disable_watchdog: bool = True, fake: bool = False
    ) -> LaserController:
        """The process-wide controller (created on first call).

        ``port_name`` (pyvisa resource name, ``ASRL<N>::INSTR`` for COM<N>) is
        required on the first call unless ``fake`` is set; later calls return
        the existing controller whatever the arguments.
        """
        global _instance
        if _instance is None:
            _instance = cls(port_name, disable_watchdog, fake)
        return _instance

    @classmethod
    def reset_instance(cls) -> None:
        """Forget the process-wide controller (tests; does not close the port)."""
        global _instance
        _instance = None

    def __init__(self, port_name: str | None = None, disable_watchdog: bool = True, fake: bool = False):
        self.port_name = port_name
        self.fake = fake
        self.device: Any
        if not fake:
            if not port_name:
                raise ValueError(
                    "LaserController needs the laser's serial port (pyvisa resource name, "
                    "e.g. ASRL<N>::INSTR for COM<N>); set the Port property in the Micro-Manager config."
                )
            from pyvisa import ResourceManager

            self.rm = ResourceManager()
            self.device = self._setup_device(port_name)
            wdt = self.get_watchdog_time()
            if wdt > 0 and disable_watchdog:
                self.set_watchdog_time(0)
                print("Disabling watchdog timer.")
            elif wdt > 0:
                warnings.warn(f"Found watchdog timer set to {wdt:0.1f} seconds.", stacklevel=2)
        else:
            from .fake_device import FakeDevice

            self.device = FakeDevice()

        self.min_wavelength = int(self.device.query("wav:min?"))
        self.max_wavelength = int(self.device.query("wav:max?"))
        self.max_wavelenth = self.max_wavelength  # historical misspelling, kept for callers

    def _setup_device(self, port_name: str) -> Any:
        """Open the serial resource and configure it as the manual specifies."""
        device = self.rm.open_resource(port_name)
        device.baud_rate = 115200
        device.read_termination = "\n"
        device.write_termination = "\n"
        return device

    # ------------------------------------------------------------------ power

    def power_on(self, blocking: bool = True, verbose: bool = False) -> None:
        """Turn the laser on (status must be 25 = ready).

        With ``blocking`` wait until the status reaches 50 (running); this
        typically takes a few minutes.
        """
        status = self.get_status()
        if status != 25:
            raise ValueError(f"Laser is not ready to turn on. Found status number {status}")
        self.device.write("on")

        if blocking:
            count = 0
            while True:
                time.sleep(1)
                count += 1
                status = self.get_status()
                if verbose:
                    print(f"{count} s - {status=:03d}\r")
                if status == 50:
                    break

    def power_off(self) -> None:
        """Turn off the laser diodes but leave the ovens on for quick restart."""
        self.device.write("off")

    def shutdown(self) -> None:
        """Fully power down the laser to prepare for switching off the mains."""
        self.device.write("shutdown")

    # ------------------------------------------------------------------ status

    def get_status(self) -> int:
        """State number (see Appendix B of the manual: 25 ready, 50 running, 60 align)."""
        return state_number(self.device.query("*stb?"))

    def get_status_word(self) -> int:
        return int(self.device.query("*stb?"))

    # ------------------------------------------------------------------ wavelength

    def set_wavelength(self, wav: int | float) -> None:
        """Set the pump wavelength in nm (within the laser's min/max)."""
        wav = int(wav)
        if not self.min_wavelength <= wav <= self.max_wavelength:
            raise ValueError(f"Require {self.min_wavelength} <= wav <= {self.max_wavelength}. Found {wav=}.")
        self.device.write(f"wav {wav}")

    def get_wavelength(self) -> int:
        return int(self.device.query("read:wav?"))

    # ------------------------------------------------------------------ readings

    def get_power(self) -> float:
        return float(self.device.query("read:pow?"))

    def get_mode(self) -> str:
        return str(self.device.query("MODE?"))

    def get_mtrpos(self) -> float:
        """DeepSee motor (GDD compensation) position."""
        return float(self.device.query("control:dsmpos?"))

    def set_mtrpos(self, pos: float) -> None:
        self.device.write(f"control:mtrmov {pos}")

    def get_history(self) -> str:
        """History buffer of status codes."""
        return str(self.device.query("READ:AHIStory?"))

    def get_humidity(self) -> float:
        return float(self.device.query("READ:HUM?"))

    def get_pct_warmup(self) -> float:
        return float(self.device.query("read:pctwarmedup?"))

    def get_current(self) -> float:
        return float(self.device.query("READ:PLASer:DIODe1:CURRent?"))

    def get_temperature(self) -> float:
        return float(self.device.query("READ:PLASer:DIODe1:TEMPerature?"))

    def get_diode_hours(self) -> float:
        return float(self.device.query("READ:PLASer:DIODe1:HOURS"))

    # ------------------------------------------------------------------ shutters

    def open_pump_shutter(self) -> None:
        self.device.write("shut 1")

    def close_pump_shutter(self) -> None:
        self.device.write("shut 0")

    def open_IR_shutter(self) -> None:  # noqa: N802
        self.device.write("irshut 1")

    def close_IR_shutter(self) -> None:  # noqa: N802
        self.device.write("irshut 0")

    def pump_shutter_state(self) -> bool:
        return bool(self.get_status_word() & (1 << BIT_MAIN_SHUTTER))

    def IR_shutter_state(self) -> bool:  # noqa: N802
        return bool(self.get_status_word() & (1 << BIT_IR_SHUTTER))

    # ------------------------------------------------------------------ watchdog / mode

    def get_watchdog_time(self) -> float:
        """Seconds without communication after which the laser powers off (0 = disabled)."""
        return float(self.device.query("tim:watc?"))

    def set_watchdog_time(self, seconds: int | float) -> None:
        self.device.write(f"tim:watc {seconds}")

    def set_mode_run(self) -> None:
        self.device.write("MODE RUN")

    def set_mode_align(self) -> None:
        self.device.write("MODE ALIGN")

    # ------------------------------------------------------------------ close

    def close(self) -> None:
        """Re-arm the watchdog, close the shutters, power off, close the port."""
        self.set_watchdog_time(3)
        self.close_pump_shutter()
        self.close_IR_shutter()
        self.power_off()
        self.device.close()
