"""Finding the Micro-Manager core a widget should talk to."""

from __future__ import annotations

from typing import Any

from pymmcore_plus import CMMCorePlus, DeviceType


def find_core(mmcore: CMMCorePlus | None = None) -> CMMCorePlus:
    """Return ``mmcore`` if given, else napari-micromanager's core, else the global one.

    napari-micromanager 0.3 owns its own core (it does not use
    ``CMMCorePlus.instance()``) and exposes it through ``get_core()``; that
    call raises when no napari-micromanager window is open, in which case we
    fall back to the process-wide instance.
    """
    if mmcore is not None:
        return mmcore
    try:
        from napari_micromanager import get_core

        return get_core()
    except Exception:
        return CMMCorePlus.instance()


def py_devices_named(core: Any, device_name: str, device_type: DeviceType | None = None) -> list[str]:
    """Labels of the loaded *Python* devices whose class name is ``device_name``."""
    try:
        labels = core.getLoadedDevicesOfType(device_type) if device_type is not None else core.getLoadedDevices()
    except Exception:
        return []
    is_py = getattr(core, "isPyDevice", None)
    out: list[str] = []
    for label in labels:
        try:
            if is_py is not None and not is_py(label):
                continue
            if core.getDeviceName(label) == device_name:
                out.append(label)
        except Exception:
            continue
    return out
