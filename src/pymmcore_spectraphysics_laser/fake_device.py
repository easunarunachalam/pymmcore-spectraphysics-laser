"""
In-memory stand-in for the laser's pyvisa serial resource.

Implements the subset of the InSight / DeepSee command set that
:class:`~pymmcore_spectraphysics_laser.controller.LaserController` uses, with
a simulated retune (``retune_time_s`` per wavelength change).  Used for
tests and for running the software without the laser
(``LaserController.instance(fake=True)`` or the device's ``Simulate=Yes``).
"""

from __future__ import annotations

import time

from .status_codes import BIT_EMISSION, BIT_IR_SHUTTER, BIT_MAIN_SHUTTER, BIT_PULSING


class FakeDevice:
    """Simulated ``pyvisa`` serial instrument."""

    retune_time_s: float = 0.0  # class attribute: how long a wavelength change takes

    def __init__(self, min_wavelength: int = 680, max_wavelength: int = 1300, wavelength: int = 800) -> None:
        self.min_wavelength = min_wavelength
        self.max_wavelength = max_wavelength
        self._wavelength = wavelength
        self._target = wavelength
        self._t_reach = 0.0
        self.state = 50  # running
        self.mode = "RUN"
        self.main_shutter = False
        self.ir_shutter = False
        self.watchdog_s = 0.0
        self.motor_pos = 12.5
        self.power_w = 1.23
        self.history: list[int] = [50, 50, 25, 25, 0]
        self.closed = False
        # attributes LaserController sets on the resource
        self.baud_rate = 115200
        self.read_termination = "\n"
        self.write_termination = "\n"
        self.log: list[str] = []

    # ------------------------------------------------------------------ model

    def _update(self) -> None:
        if self._wavelength != self._target and time.monotonic() >= self._t_reach:
            self._wavelength = self._target

    def status_word(self) -> int:
        self._update()
        w = (self.state & 0x7F) << 16
        if self.state >= 50:
            w |= (1 << BIT_EMISSION) | (1 << BIT_PULSING)
        if self.main_shutter:
            w |= 1 << BIT_MAIN_SHUTTER
        if self.ir_shutter:
            w |= 1 << BIT_IR_SHUTTER
        return w

    @property
    def wavelength(self) -> int:
        self._update()
        return self._wavelength

    # ------------------------------------------------------------------ pyvisa API

    def query(self, cmd: str) -> str:
        self.log.append(cmd)
        c = cmd.strip().lower()
        if c == "wav:min?":
            return str(self.min_wavelength)
        if c == "wav:max?":
            return str(self.max_wavelength)
        if c == "read:wav?":
            return str(self.wavelength)
        if c == "*stb?":
            return str(self.status_word())
        if c == "read:pow?":
            return f"{self.power_w:.3f}"
        if c == "mode?":
            return self.mode
        if c == "control:dsmpos?":
            return f"{self.motor_pos:.2f}"
        if c == "read:ahistory?":
            return " ".join(str(h) for h in self.history)
        if c == "read:hum?":
            return "3.200"
        if c == "read:pctwarmedup?":
            return "100"
        if c == "read:plaser:diode1:current?":
            return "25.00"
        if c == "read:plaser:diode1:temperature?":
            return "23.50"
        if c == "read:plaser:diode1:hours":
            return "1234"
        if c == "tim:watc?":
            return f"{self.watchdog_s:.1f}"
        raise ValueError(f"FakeDevice: unknown query {cmd!r}")

    def write(self, cmd: str) -> None:
        self.log.append(cmd)
        c = cmd.strip()
        cl = c.lower()
        if cl.startswith("wav "):
            wav = int(cl.split()[1])
            if not self.min_wavelength <= wav <= self.max_wavelength:
                return  # the real laser ignores out-of-range values
            if wav != self._target:
                self._target = wav
                self._t_reach = time.monotonic() + self.retune_time_s
            return
        if cl == "on":
            self.state = 50
            return
        if cl == "off":
            self.state = 25
            return
        if cl == "shutdown":
            self.state = 0
            return
        if cl.startswith("shut "):
            self.main_shutter = cl.split()[1] == "1"
            return
        if cl.startswith("irshut "):
            self.ir_shutter = cl.split()[1] == "1"
            return
        if cl.startswith("tim:watc "):
            self.watchdog_s = float(cl.split()[1])
            return
        if cl == "mode run":
            self.mode = "RUN"
            self.state = 50
            return
        if cl == "mode align":
            self.mode = "ALIGN"
            self.state = 60
            return
        if cl.startswith("control:mtrmov "):
            self.motor_pos = float(cl.split()[1])
            return
        raise ValueError(f"FakeDevice: unknown command {cmd!r}")

    def close(self) -> None:
        self.closed = True
