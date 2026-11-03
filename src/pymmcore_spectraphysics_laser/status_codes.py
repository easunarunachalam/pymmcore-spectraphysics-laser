"""Helpers for decoding InSight / DeepSee ``*STB?`` status words.

Derived from davy-jones by John Russell (MIT licence, see LICENSE-davy-jones).
"""

from __future__ import annotations


def state_number(status: str | int) -> int:
    """The 7-bit state number held in bits 16-22 of the status word."""
    mask = 0x007F0000
    return int((int(status) & mask) >> 16)


def state_defs(status: str | int) -> str:
    x = state_number(status)

    if x < 0 or x > 127:
        raise ValueError("Invalid State Code")
    elif x < 25:
        return "Initializing"
    elif x == 25:
        return "Ready"
    elif 25 < x < 50:
        return "Turning On/Optimizing"
    elif x == 50:
        return "Running"
    elif 50 < x < 60:
        return "Moving to align mode"
    elif x == 60:
        return "Align mode"
    elif 60 < x < 70:
        return "Exiting align mode"
    else:
        return "Reserved state"


# bit -> meaning of the low 16 bits of the status word
INTERPRETATION = [
    "Emission",
    "Pulsing",
    "Main Shutter",
    "IR Shutter",
    "Reserved",
    "Servo On",
    "Reserved",
    "Reserved",
    "Reserved",
    "User Interlock",
    "Keyswitch",
    "Power Supply",
    "Internal",
    "Reserved",
    "Warning",
    "Fault",
]

DESCRIPTIONS = [
    ["Diodes are not energized", "Diodes are energized"],
    ["Laser is not running", "Laser is in RUN/ALIGN mode"],
    ["Main shutter is closed", "Main shutter is open"],
    ["IR shutter is closed", "IR shutter is open"],
    ["", ""],
    ["Servo is off", "Servo is on"],
    ["", ""],
    ["", ""],
    ["", ""],
    ["Interlock closed", "Interlock open - laser is forced off"],
    ["Interlock closed", "Interlock open - laser is forced off"],
    ["Interlock closed", "Interlock open - laser is forced off"],
    ["Interlock closed", "Interlock open - laser is forced off"],
    ["", ""],
    ["No warnings", "Warning detected -- use read_history to investigate"],
    [
        "No faults",
        "Fault detected. Laser will not run. Use read_history to investigate",
    ],
]

# status-word bit positions used by the controller
BIT_EMISSION = 0
BIT_PULSING = 1
BIT_MAIN_SHUTTER = 2
BIT_IR_SHUTTER = 3
