# pymmcore-spectraphysics-laser

Spectra-Physics **InSight / DeepSee** tunable laser for
[pymmcore-plus](https://github.com/pymmcore-plus/pymmcore-plus) /
[napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager):

* `LaserController` - the serial (pyvisa) interface (power, wavelength,
  shutters, run/align mode, diagnostics).  Successor of the
  `spectraphysics_control` repo (itself derived from John Russell's
  davy-jones, MIT; see `LICENSE-davy-jones`).
* `SpectraPhysicsLaser` - a pure-Python Micro-Manager device: the wavelength
  is a settable property, so it can be part of a channel preset, and the
  device is *busy* while retuning (plus a settle time), so the MDA engine
  waits for it.
* `LaserControlWidget` - the Qt control panel
  (`Plugins > Spectra-Physics Laser > Laser Control` in napari).
* `fake_device.FakeDevice` - a simulator for developing without the laser.

**Disclaimer:** This software is provided "as is", without warranty of any
kind. There is no guarantee that it works, that it is fit for any purpose, or
that it will not damage your hardware, your data or your computer. The authors
accept no liability for any such damage. See [LICENSE](LICENSE).

## Install

```powershell
pip install -e ".[napari,test]"
```

Requirements: pymmcore-plus 0.18.x (the Python-device layer `UniMMCore` is
still under `pymmcore_plus.experimental`, so the version is pinned
deliberately), napari-micromanager 0.3.x with a Qt6 binding (PyQt6).

## Device in the config file

The serial port and the per-channel wavelengths are **setup choices and live
in your Micro-Manager config file only**; the package has no defaults for
them.

```
#py pyDevice,Laser,pymmcore_spectraphysics_laser,SpectraPhysicsLaser
#py Property,Laser,Port,ASRL<N>::INSTR        # COM<N>

#py ConfigGroup,channel,<preset>,Laser,Wavelength,<nm>
```

| property | meaning |
|---|---|
| `Port` (pre-init) | pyvisa resource name of the serial port (`ASRL<N>::INSTR` for COM<N>); required unless simulating |
| `Simulate` (pre-init) | `Yes` uses the simulator instead of hardware |
| `Wavelength` | pump wavelength in nm, settable, preset-able |
| `SettleTimeS` | seconds the device stays busy after reaching the wavelength (default 10) |
| `Status`, `Power` | read-only |

Every preset of a group must set the same properties (Micro-Manager
convention, enforced by the napari-micromanager widgets).

## Panel

`Plugins > Spectra-Physics Laser > Laser Control` in napari (no launcher
code: the widget finds the `SpectraPhysicsLaser` device in
napari-micromanager's core and shares its serial connection, retrying until a
config with the device is loaded).  Or, in your own Qt code:

```python
from pymmcore_spectraphysics_laser import LaserControlWidget, locked_laser_controller
w = LaserControlWidget(mmcore=core)   # uses the Port of the SpectraPhysicsLaser device in `core`
# or, without a Micro-Manager device: LaserControlWidget(locked_laser_controller("ASRL<N>::INSTR"))
```

All access to the laser goes through one process-wide `LaserController`
(`LaserController.instance()`) behind a lock (`locked_laser_controller()`),
so the panel's polling and the Micro-Manager device never talk over each
other.

## Preset workarounds

Importing this package (which loading the config does) applies two small
runtime fixes to pymmcore-widgets' preset dropdown, needed for presets that
contain Python devices (its `configSet` handler runs before the Python
devices are applied, and it can re-select and *apply* the last preset when
its `<no match>` entry is removed); see
`src/pymmcore_spectraphysics_laser/_compat.py` (identical to the one in
pymmcore-kinesis; whichever is imported first applies them).
`PYMMCORE_PYDEVICE_NO_WORKAROUNDS=1` disables them.

## Tests

```powershell
python -m pytest
```
