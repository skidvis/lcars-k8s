"""LCARS colours, in two flavours.

The default is the real palette in 24-bit colour. On a 16-colour terminal —
the Linux virtual console, most notably — those hex values collapse to the
nearest ANSI slot, and LCARS orange lands on *red*, which turns the whole
interface into a red alert. So console mode picks the ANSI colours by hand
instead of letting the terminal round them, and snaps gradients to discrete
steps rather than interpolating between shades that don't exist.

Call :func:`set_mode` once, before anything imports the app.
"""

from __future__ import annotations

import os
from typing import Sequence

MODE = "colour"  # "colour" | "kmscon" | "fbterm" | "console"

_NAMES = ("BLACK", "ORANGE", "BUTTERSCOTCH", "ALMOND", "TAN", "SUNFLOWER",
          "GOLDENROD", "LILAC", "VIOLET", "PERIWINKLE", "ANAKIWA", "ICE",
          "MARS", "TOMATO", "SPACE_WHITE", "GREY", "DIM")

_COLOUR = {
    "BLACK": "#000000",
    "ORANGE": "#FF9900",        # the LCARS workhorse
    "BUTTERSCOTCH": "#FF9966",
    "ALMOND": "#FFAA90",
    "TAN": "#FFCC99",
    "SUNFLOWER": "#FFCC00",
    "GOLDENROD": "#FFCC66",
    "LILAC": "#CC99CC",         # "African violet"
    "VIOLET": "#9944FF",
    "PERIWINKLE": "#9999FF",
    "ANAKIWA": "#99CCFF",
    "ICE": "#CCDDFF",
    "MARS": "#CC4444",
    "TOMATO": "#DD6644",
    "SPACE_WHITE": "#F5F6FA",
    "GREY": "#5C5C7A",
    "DIM": "#3A2A18",
}

# Hand-picked ANSI equivalents. Yellow carries the orange family, because it
# is the only warm colour among the sixteen that isn't an alarm.
_CONSOLE = {
    "BLACK": "black",
    "ORANGE": "bright_yellow",
    "BUTTERSCOTCH": "yellow",
    "ALMOND": "yellow",
    "TAN": "white",
    "SUNFLOWER": "yellow",
    "GOLDENROD": "yellow",
    "LILAC": "bright_magenta",
    "VIOLET": "magenta",
    "PERIWINKLE": "bright_blue",
    "ANAKIWA": "bright_cyan",
    "ICE": "bright_white",
    "MARS": "bright_red",
    "TOMATO": "red",
    "SPACE_WHITE": "bright_white",
    "GREY": "bright_black",
    "DIM": "bright_black",
}

_LOAD_COLOUR = ((0.00, "#6C7FE0"), (0.30, "#CC99CC"), (0.55, "#FF9900"),
                (0.80, "#FF9966"), (1.00, "#CC4444"))
_MEM_COLOUR = ((0.00, "#7A6CB8"), (0.30, "#99CCFF"), (0.55, "#FFCC00"),
               (0.80, "#FFAA90"), (1.00, "#CC4444"))

_LOAD_CONSOLE = ((0.00, "bright_blue"), (0.35, "bright_magenta"),
                 (0.60, "yellow"), (0.82, "bright_yellow"), (1.00, "bright_red"))
_MEM_CONSOLE = ((0.00, "blue"), (0.35, "bright_cyan"),
                (0.60, "bright_magenta"), (0.82, "bright_yellow"),
                (1.00, "bright_red"))

# Filled in by set_mode(); declared here so the module's exports are visible.
BLACK = ORANGE = BUTTERSCOTCH = ALMOND = TAN = SUNFLOWER = GOLDENROD = ""
LILAC = VIOLET = PERIWINKLE = ANAKIWA = ICE = MARS = TOMATO = ""
SPACE_WHITE = GREY = DIM = ""
LOAD_STOPS: tuple[tuple[float, str], ...] = ()
MEM_STOPS: tuple[tuple[float, str], ...] = ()
ROTATION: tuple[str, ...] = ()

_STATUS = {
    "Running": "ANAKIWA", "Succeeded": "PERIWINKLE", "Completed": "PERIWINKLE",
    "Pending": "SUNFLOWER", "ContainerCreating": "SUNFLOWER",
    "PodInitializing": "SUNFLOWER", "Init": "SUNFLOWER",
    "Terminating": "LILAC", "Failed": "MARS", "Error": "MARS",
    "CrashLoopBackOff": "MARS", "ImagePullBackOff": "MARS",
    "ErrImagePull": "MARS", "OOMKilled": "MARS", "Evicted": "TOMATO",
    "NotReady": "TOMATO", "Unknown": "GREY",
}


def set_mode(mode: str) -> None:
    """Switch the whole palette between rich and 16-colour ANSI output."""
    global MODE, LOAD_STOPS, MEM_STOPS, ROTATION
    MODE = mode if mode in ("colour", "kmscon", "fbterm", "console") else "colour"
    table = _CONSOLE if MODE == "console" else _COLOUR
    globals().update({name: table[name] for name in _NAMES})
    LOAD_STOPS = _LOAD_CONSOLE if MODE == "console" else _LOAD_COLOUR
    MEM_STOPS = _MEM_CONSOLE if MODE == "console" else _MEM_COLOUR
    ROTATION = (ORANGE, LILAC, TAN, PERIWINKLE, BUTTERSCOTCH, ANAKIWA)


def detect_mode() -> str:
    """Guess whether this terminal can show the real palette.

    The Linux virtual console is the case that matters: sixteen colours and a
    font with no braille. Everything else is assumed capable.
    """
    term = os.environ.get("TERM", "")
    if term == "fbterm":
        return "fbterm"
    if term in ("linux", "dumb", "vt100", "vt220", "ansi", "cons25"):
        return "console"
    return "colour"


def css(colour: str) -> str:
    """Render a palette value as something Textual CSS will accept."""
    return colour if colour.startswith("#") else f"ansi_{colour}"


def status_colour(status: str) -> str:
    if status in _STATUS:
        return globals()[_STATUS[status]]
    for key, name in _STATUS.items():
        if key.lower() in status.lower():
            return globals()[name]
    return TAN


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def gradient(fraction: float, stops: Sequence[tuple[float, str]] | None = None) -> str:
    """Pick a colour off a ramp.

    Interpolates in truecolor. In console mode there is nothing to interpolate
    between, so it snaps to the nearest step at or below the value.
    """
    stops = stops or LOAD_STOPS
    f = max(0.0, min(1.0, fraction))

    if MODE == "console":
        chosen = stops[0][1]
        for position, colour in stops:
            if f >= position:
                chosen = colour
        return chosen

    prev_pos, prev_col = stops[0]
    for position, colour in stops:
        if f <= position:
            if position == prev_pos:
                return colour
            t = (f - prev_pos) / (position - prev_pos)
            a, b = hex_to_rgb(prev_col), hex_to_rgb(colour)
            return rgb_to_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])
        prev_pos, prev_col = position, colour
    return stops[-1][1]


def shade(colour: str, factor: float) -> str:
    """Push a colour toward black (factor < 1) or white (factor > 1)."""
    if not colour.startswith("#"):
        if factor > 1 and not colour.startswith("bright_") and colour != "white":
            return f"bright_{colour}"
        return colour
    r, g, b = hex_to_rgb(colour)
    if factor <= 1:
        return rgb_to_hex([r * factor, g * factor, b * factor])
    t = min(1.0, factor - 1.0)
    return rgb_to_hex([r + (255 - r) * t, g + (255 - g) * t, b + (255 - b) * t])


set_mode("colour")
