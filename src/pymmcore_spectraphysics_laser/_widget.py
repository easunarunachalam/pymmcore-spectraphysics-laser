"""
Qt control panel for the Spectra-Physics laser: status, on/off, run/align
mode, power, wavelength, DeepSee motor position, shutters, diagnostics.

Works as a napari plugin dock widget (``Plugins > Spectra-Physics Laser >
Laser Control``): napari constructs it with no arguments, and it looks for a
:class:`SpectraPhysicsLaser` device in the core napari-micromanager is using
and shares that device's serial connection.  It can also be embedded in any
Qt app with an explicit ``laser_controller`` or ``mmcore``.

Derived from davy-jones by John Russell (MIT licence, see LICENSE-davy-jones).
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Union

from qtpy.QtCore import QSize, Qt, QTimer
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ._core import find_core, py_devices_named
from ._device import SpectraPhysicsLaser, locked_laser_controller

__all__ = ["LaserControlWidget", "laser_device_labels"]

COLOR_TYPE = Union[QColor, int, str, Qt.GlobalColor, "tuple[int, int, int, int]", "tuple[int, int, int]"]

NO_DEVICE_TEXT = "No SpectraPhysicsLaser device is loaded in Micro-Manager."

# status changes shown by the panel (a launcher can route this logger into its session log)
_log = logging.getLogger(__name__)


def laser_device_labels(core: Any) -> list[str]:
    """Labels of the SpectraPhysicsLaser devices loaded in ``core``."""
    return py_devices_named(core, SpectraPhysicsLaser.name())


def _icon(name: str, color: COLOR_TYPE) -> Any:
    from fonticon_mdi6 import MDI6
    from superqt.fonticon import icon

    return icon(getattr(MDI6, name), color=color)


class LaserControlWidget(QWidget):
    """Control panel for a Spectra-Physics InSight / DeepSee laser.

    Parameters
    ----------
    laser_controller :
        A (lock-protected) :class:`LaserController`.  ``None`` means: find a
        :class:`SpectraPhysicsLaser` device in the Micro-Manager core and use
        its connection (retried every ``retry_ms`` and whenever a config is
        loaded until one appears).
    mmcore :
        Core to look in; ``None`` = the one napari-micromanager is using.
    napari_viewer :
        Injected by napari; unused.
    """

    STATUS_POLL_MS = 1000
    DISPLAY_POLL_MS = 500

    def __init__(
        self,
        laser_controller: Any = None,
        *,
        mmcore: Any = None,
        napari_viewer: Any = None,
        parent: QWidget | None = None,
        retry_ms: int = 2000,
    ) -> None:
        super().__init__(parent=parent)

        self.laser_controller: Any = None
        self._explicit_core = mmcore
        self._core: Any = None
        self._logged: dict[str, str] = {}  # last value logged per readout (status, wavelength, shutters)

        self._icon_open = "hexagon_outline"
        self._icon_closed = "hexagon_slice_6"
        self._icon_color_open: COLOR_TYPE = (0, 255, 0)
        self._icon_color_closed: COLOR_TYPE = "magenta"
        self._icon_size = 25
        self._button_text_on = "ON"
        self._button_text_off = "OFF"
        self._button_text_open = "OPEN"
        self._button_text_closed = "CLOSED"

        self.setWindowTitle("Spectra-Physics Laser Control")
        self._build_ui()

        # periodically update internal status variables / the display
        self.timer_updateinternals = QTimer(self)
        self.timer_updateinternals.timeout.connect(self.update_internal_status)
        self.timer_displaystatus = QTimer(self)
        self.timer_displaystatus.timeout.connect(self.update_display_status)

        # until a controller is attached, look for a laser device in the core
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(retry_ms)
        self._retry_timer.timeout.connect(self._try_attach_from_core)

        self.destroyed.connect(self._disconnect_core)

        if laser_controller is not None:
            self.attach(laser_controller)
        else:
            self.status_string.setText(NO_DEVICE_TEXT)
            self._try_attach_from_core()
            if self.laser_controller is None:
                self._retry_timer.start()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.layout_ = QFormLayout()

        self.status_label = QLabel("Laser status:")
        self.status_string = QLineEdit("")
        self.status_string.setReadOnly(True)
        self.layout_.addRow(self.status_label, self.status_string)

        self.laser_onoff_label = QLabel("Laser On/Off:")
        self.laser_status = -1  # state number; -1 = not read yet
        self.laser_onoff_button = QPushButton(text=self._button_text_off)
        self.laser_onoff_button.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self.laser_onoff_button.setIcon(_icon(self._icon_closed, self._icon_color_closed))
        self.laser_onoff_button.setIconSize(QSize(self._icon_size, self._icon_size))
        self.laser_onoff_button.clicked.connect(self.on_laser_onoff_button_clicked)
        self.layout_.addRow(self.laser_onoff_label, self.laser_onoff_button)

        self.toggle_mode_label = QLabel("Run / Align mode:")
        self.toggle_mode_status = "Run"
        self.toggle_mode_button = QPushButton("Running mode (press to switch to Align)", self)
        self.toggle_mode_button.setCheckable(True)
        self.toggle_mode_button.clicked.connect(self.on_toggle_mode_change)
        self.layout_.addRow(self.toggle_mode_label, self.toggle_mode_button)

        self.power_label = QLabel("Power (W):")
        self.power_status = QLineEdit("")
        self.power_status.setReadOnly(True)
        self.layout_.addRow(self.power_label, self.power_status)

        self.wavelength_label = QLabel("Wavelength (nm):")
        self.wavelength_status = QLineEdit("")
        self.wavelength_status.setReadOnly(True)
        self.wavelength_edit = QLineEdit()
        self.wavelength_edit.setPlaceholderText("target")
        self.wavelength_edit.editingFinished.connect(self.update_wavelength)
        row = QHBoxLayout()
        row.addWidget(self.wavelength_status)
        row.addWidget(self.wavelength_edit)
        self.layout_.addRow(self.wavelength_label, row)

        self.ds_label = QLabel("Motor Pos:")
        self.ds_status = QLineEdit("")
        self.ds_status.setReadOnly(True)
        self.ds_edit = QLineEdit()
        self.ds_edit.setPlaceholderText("target")
        self.ds_edit.editingFinished.connect(self.update_motor_position)
        row = QHBoxLayout()
        row.addWidget(self.ds_status)
        row.addWidget(self.ds_edit)
        self.layout_.addRow(self.ds_label, row)

        self.pump_shutter_label = QLabel("Pump Beam Shutter:")
        self.pump_shutter_status = -1  # 0 closed, 1 open, -1 unknown
        self.pump_shutter_button = QPushButton(text=self._button_text_closed)
        self.pump_shutter_button.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self.pump_shutter_button.setIcon(_icon(self._icon_closed, self._icon_color_closed))
        self.pump_shutter_button.setIconSize(QSize(self._icon_size, self._icon_size))
        self.pump_shutter_button.clicked.connect(self.on_pump_shutter_button_clicked)
        self.layout_.addRow(self.pump_shutter_label, self.pump_shutter_button)

        self.IR_shutter_label = QLabel("IR Beam Shutter:")
        self.IR_shutter_status = -1
        self.IR_shutter_button = QPushButton(text=self._button_text_closed)
        self.IR_shutter_button.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self.IR_shutter_button.setIcon(_icon(self._icon_closed, self._icon_color_closed))
        self.IR_shutter_button.setIconSize(QSize(self._icon_size, self._icon_size))
        self.IR_shutter_button.clicked.connect(self.on_IR_shutter_button_clicked)
        self.layout_.addRow(self.IR_shutter_label, self.IR_shutter_button)

        self.mode_status = QLineEdit("")
        self.mode_status.setReadOnly(True)
        self.layout_.addRow(QLabel("Mode:"), self.mode_status)

        self.temperature_status = QLineEdit("")
        self.temperature_status.setReadOnly(True)
        self.layout_.addRow(QLabel("Temperature:"), self.temperature_status)

        self.humidity_status = QLineEdit("")
        self.humidity_status.setReadOnly(True)
        self.layout_.addRow(QLabel("Humidity:"), self.humidity_status)

        self.current_status = QLineEdit("")
        self.current_status.setReadOnly(True)
        self.layout_.addRow(QLabel("Current:"), self.current_status)

        self.history_buffer_status = QLineEdit("")
        self.history_buffer_status.setReadOnly(True)
        self.layout_.addRow(QLabel("History Buffer:"), self.history_buffer_status)

        self.setLayout(self.layout_)

    # ------------------------------------------------------------------ attaching

    @property
    def core(self) -> Any:
        return self._core

    def attach(self, laser_controller: Any) -> None:
        """Use ``laser_controller`` from now on and start polling it."""
        self.laser_controller = laser_controller
        self._retry_timer.stop()
        self.update_internal_status()
        self.update_display_status()
        self.timer_updateinternals.start(self.STATUS_POLL_MS)
        self.timer_displaystatus.start(self.DISPLAY_POLL_MS)

    def _try_attach_from_core(self, *_: Any) -> None:
        if self.laser_controller is not None:
            return
        try:
            core = find_core(self._explicit_core)
        except Exception:
            return
        if core is not self._core:
            self._disconnect_core()
            self._core = core
            try:
                core.events.systemConfigurationLoaded.connect(self._try_attach_from_core)
            except Exception:
                pass
        labels = laser_device_labels(core)
        if not labels:
            return
        label = labels[0]
        try:
            port = str(core.getProperty(label, "Port"))
            fake = str(core.getProperty(label, "Simulate")) == "Yes"
        except Exception:
            return
        self.attach(locked_laser_controller(port, fake=fake))

    def _disconnect_core(self, *_: Any) -> None:
        if self._core is not None:
            try:
                self._core.events.systemConfigurationLoaded.disconnect(self._try_attach_from_core)
            except Exception:
                pass

    # ------------------------------------------------------------------ polling

    def _log_change(self, what: str, text: str) -> None:
        """One log line per *change* of a readout, not one per poll."""
        if self._logged.get(what) != text:
            self._logged[what] = text
            _log.info("laser %s: %s", what, text)

    def update_internal_status(self) -> None:
        """Read state and shutters (once per STATUS_POLL_MS)."""
        ctrl = self.laser_controller
        if ctrl is None:
            return
        try:
            self.laser_status = ctrl.get_status()
            self.pump_shutter_status = int(ctrl.pump_shutter_state())
            self.IR_shutter_status = int(ctrl.IR_shutter_state())
        except Exception as e:
            self.status_string.setText(f"communication error: {e}")
            self._log_change("status", f"communication error: {e}")
            return
        self._log_change("pump shutter", "open" if self.pump_shutter_status else "closed")
        self._log_change("IR shutter", "open" if self.IR_shutter_status else "closed")

        if self.laser_status == 50:
            self.laser_onoff_button.setIcon(_icon(self._icon_open, self._icon_color_open))
            self.laser_onoff_button.setText(self._button_text_on)
            self.toggle_mode_status = "Run"
        elif self.laser_status == 60:
            self.laser_onoff_button.setIcon(_icon(self._icon_open, self._icon_color_open))
            self.laser_onoff_button.setText(self._button_text_on)
            self.toggle_mode_status = "Align"
        else:
            self.laser_onoff_button.setIcon(_icon(self._icon_closed, self._icon_color_closed))
            self.laser_onoff_button.setText(self._button_text_off)

        for status, button in (
            (self.pump_shutter_status, self.pump_shutter_button),
            (self.IR_shutter_status, self.IR_shutter_button),
        ):
            if status == 0:
                button.setIcon(_icon(self._icon_closed, self._icon_color_closed))
                button.setText(self._button_text_closed)
            elif status == 1:
                button.setIcon(_icon(self._icon_open, self._icon_color_open))
                button.setText(self._button_text_open)

    def update_display_status(self) -> None:
        """Refresh the readouts (once per DISPLAY_POLL_MS)."""
        ctrl = self.laser_controller
        if ctrl is None:
            return
        try:
            s = self.laser_status
            if 0 <= s <= 24:
                self.status_string.setText("Initializing... (not ready to turn on)")
            elif s == 25:
                self.status_string.setText("Ready to turn on")
            elif 26 <= s <= 49:
                self.status_string.setText("Turning on...")
            elif s == 50:
                self.status_string.setText("Running mode")
            elif 51 <= s <= 59:
                self.status_string.setText("Initializing alignment mode...")
            elif s == 60:
                self.status_string.setText("Alignment mode")
            elif 61 <= s <= 69:
                self.status_string.setText("Exiting alignment mode...")
            elif 70 <= s <= 127:
                self.status_string.setText(f"Reserved status code {s:3d}")
            else:
                self.status_string.setText(f"Invalid status code {s:3d}")
            self._log_change("status", self.status_string.text())

            self.power_status.setText(f"{ctrl.get_power():2.2f}")
            self.wavelength_status.setText(f"{ctrl.get_wavelength():3d}")
            self._log_change("wavelength", f"{self.wavelength_status.text()} nm")
            self.ds_status.setText(f"{ctrl.get_mtrpos():2.2f}")
            self.mode_status.setText(str(ctrl.get_mode()))
            self.temperature_status.setText(f"{ctrl.get_temperature():2.2f}")
            self.humidity_status.setText(f"{ctrl.get_humidity():2.3f}")
            self.current_status.setText(f"{ctrl.get_current():2.2f}")
            self.history_buffer_status.setText(str(ctrl.get_history())[:32])  # last few codes
        except Exception as e:
            self.status_string.setText(f"communication error: {e}")
            self._log_change("status", f"communication error: {e}")

    # ------------------------------------------------------------------ actions

    def on_toggle_mode_change(self) -> None:
        if self.laser_controller is None:
            return
        if self.toggle_mode_status == "Run":
            self.toggle_mode_status = "Align"
            self.laser_controller.set_mode_align()
            self.toggle_mode_button.setText("Alignment mode (press to switch to Run)")
        elif self.toggle_mode_status == "Align":
            self.toggle_mode_status = "Run"
            self.laser_controller.set_mode_run()
            self.toggle_mode_button.setText("Running mode (press to switch to Align)")

    def on_pump_shutter_button_clicked(self) -> None:
        if self.laser_controller is None:
            return
        if self.pump_shutter_status == 0:
            self.laser_controller.open_pump_shutter()
        elif self.pump_shutter_status == 1:
            self.laser_controller.close_pump_shutter()
        else:
            warnings.warn(f"Unknown pump shutter status ({self.pump_shutter_status}); ignoring click.", stacklevel=2)

    def on_IR_shutter_button_clicked(self) -> None:  # noqa: N802
        if self.laser_controller is None:
            return
        if self.IR_shutter_status == 0:
            self.laser_controller.open_IR_shutter()
        elif self.IR_shutter_status == 1:
            self.laser_controller.close_IR_shutter()
        else:
            warnings.warn(f"Unknown IR shutter status ({self.IR_shutter_status}); ignoring click.", stacklevel=2)

    def on_laser_onoff_button_clicked(self) -> None:
        if self.laser_controller is None:
            return
        if self.laser_status == 25:
            self.laser_controller.power_on(blocking=False)
            self.status_string.setText("Turning on...")
        elif self.laser_status == 50:
            self.laser_controller.power_off()
        else:
            warnings.warn(f"Unknown laser status ({self.laser_status}); ignoring click.", stacklevel=2)

    def update_wavelength(self) -> None:
        if self.laser_controller is None:
            return
        try:
            new_wavelength = int(round(float(self.wavelength_edit.text())))
            self.laser_controller.set_wavelength(new_wavelength)
        except ValueError as e:
            warnings.warn(f"Invalid wavelength: {e}", stacklevel=2)

    def update_motor_position(self) -> None:
        if self.laser_controller is None:
            return
        try:
            self.laser_controller.set_mtrpos(float(self.ds_edit.text()))
        except ValueError:
            warnings.warn("Invalid motor position value. Please enter a numeric value.", stacklevel=2)

    # ------------------------------------------------------------------ cached reads

    def read_wavelength(self) -> int:
        """Wavelength as last displayed (avoids querying the laser)."""
        return int(self.wavelength_status.text())

    def read_status(self) -> int:
        """State number as last polled (avoids querying the laser)."""
        return int(self.laser_status)
