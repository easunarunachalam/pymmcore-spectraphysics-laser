"""Runtime workarounds needed for config presets that contain Python devices.

They patch two methods of ``pymmcore_widgets.PresetsWidget`` (the preset
dropdown used by napari-micromanager's channel selector and its Groups and
Presets table).  Both are idempotent and shared with the other ``pymmcore-*``
device packages (same marker attribute), so whichever package is imported
first applies them.  Set ``PYMMCORE_PYDEVICE_NO_WORKAROUNDS=1`` to skip them.

1. ``_on_cfg_set`` runs synchronously inside ``UniMMCore.setConfig`` *before*
   the Python device settings of the preset are applied (the C++ part emits
   ``configSet`` first, the Python part is applied afterwards).  The widget
   therefore compares the previous preset's values and shows "<no match>".
   The patch defers the handler by one event-loop turn, i.e. until
   ``setConfig`` has returned.

2. ``_update_if_props_not_match_preset`` removes its "<no match>" combobox
   entry without blocking signals.  If that entry is current, Qt selects
   another item (the last preset alphabetically), which fires
   ``currentTextChanged`` -> ``setConfig`` and *applies* that preset.  The
   patch runs the method with the combobox signals blocked: it is a pure
   display sync and must never apply a configuration.

(``UniMMCore.setConfig`` itself cannot be patched: the core classes are SWIG
types whose metaclass rejects attribute assignment.)
"""

from __future__ import annotations

import os
from typing import Any

MARK = "_pymmcore_pydevice_preset_workaround"
ENV_DISABLE = "PYMMCORE_PYDEVICE_NO_WORKAROUNDS"


def apply_workarounds() -> None:
    if os.environ.get(ENV_DISABLE) == "1":
        return
    _patch_presets_widget()


def _patch_presets_widget() -> None:
    try:
        from pymmcore_widgets.control import _presets_widget as pw_mod
        from qtpy.QtCore import QTimer
        from superqt.utils import signals_blocked
    except Exception:
        return  # no Qt / pymmcore-widgets here (headless use): nothing to fix
    cls = pw_mod.PresetsWidget

    orig_update = cls.__dict__.get("_update_if_props_not_match_preset")
    if orig_update is not None and not getattr(orig_update, MARK, False):

        def _update_if_props_not_match_preset(self: Any) -> None:
            with signals_blocked(self._combo):
                orig_update(self)

        _update_if_props_not_match_preset.__wrapped__ = orig_update  # type: ignore[attr-defined]
        setattr(_update_if_props_not_match_preset, MARK, True)
        cls._update_if_props_not_match_preset = _update_if_props_not_match_preset

    orig_cfg_set = cls.__dict__.get("_on_cfg_set")
    if orig_cfg_set is not None and not getattr(orig_cfg_set, MARK, False):

        def _on_cfg_set(self: Any, group: str, preset: str) -> None:
            def run() -> None:
                try:
                    orig_cfg_set(self, group, preset)
                except RuntimeError:
                    pass  # widget deleted in the meantime

            QTimer.singleShot(0, run)  # after setConfig() has returned

        _on_cfg_set.__wrapped__ = orig_cfg_set  # type: ignore[attr-defined]
        setattr(_on_cfg_set, MARK, True)
        cls._on_cfg_set = _on_cfg_set
