"""Drawing primitives: btop-style braille graphs, gradient meters, and the
LCARS chrome (elbows, pills, panel bars) rendered with block characters.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from rich.style import Style
from rich.text import Text

from . import palette as P

#: Glyph repertoire in use.
#:   braille - dot graphs, quadrant chamfers, eighth-block meters. Needs a
#:             proper terminal font.
#:   block   - half blocks, shade blocks and half-width caps. For 16-colour
#:             terminals whose font still covers U+2580-259F.
#:   solid   - the full block and nothing else. The Linux virtual console font
#:             carries U+2588 and very little else, so anything fancier comes
#:             out as substitution lozenges.
#:   ascii   - no box drawing at all.
GLYPHS = "braille"

BRAILLE_BASE = 0x2800
# Dot bit masks, indexed [column][row-from-top]. Braille cells are 2x4 dots.
_DOT = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))

# Partial blocks, 1/8th steps, for sub-cell meter precision.
_PARTIAL = " ▏▎▍▌▋▊▉█"

# Quadrant blocks used to chamfer the corners of LCARS pills and elbows.
Q_TL, Q_TR, Q_BL, Q_BR = "▘", "▝", "▖", "▗"
FULL = "█"
HALF_UP, HALF_DOWN = "▀", "▄"
CAP_LEFT, CAP_RIGHT = "▐", "▌"
BODY = "▒"      # graph fill below the curve
TRACK = "█"     # unfilled part of a meter


def set_glyphs(mode: str) -> None:
    """Choose which characters the interface is allowed to draw with.

    The Linux virtual console has no braille and no quadrant blocks, so the
    chamfered corners flatten to squares and the graphs switch from dots to
    solid columns. It reads as blockier LCARS rather than as damage.
    """
    global GLYPHS, Q_TL, Q_TR, Q_BL, Q_BR, FULL, HALF_UP, HALF_DOWN
    global CAP_LEFT, CAP_RIGHT, BODY, TRACK, _PARTIAL
    GLYPHS = mode
    if mode == "ascii":
        Q_TL = Q_TR = Q_BL = Q_BR = "#"
        FULL = HALF_UP = HALF_DOWN = "#"
        CAP_LEFT = CAP_RIGHT = "|"
        BODY, TRACK = ":", "."
        _PARTIAL = "         "
    elif mode == "solid":
        # U+2588 is the only block character a console font can be relied on
        # for. Everything else degrades to it or to a space.
        Q_TL = Q_TR = Q_BL = Q_BR = "\u2588"
        FULL = HALF_UP = HALF_DOWN = "\u2588"
        CAP_LEFT = CAP_RIGHT = "\u2588"
        BODY, TRACK = "\u2588", " "
        _PARTIAL = "         "
    elif mode == "block":
        Q_TL = Q_TR = Q_BL = Q_BR = "\u2588"
        FULL, HALF_UP, HALF_DOWN = "\u2588", "\u2580", "\u2584"
        CAP_LEFT, CAP_RIGHT = "\u2590", "\u258c"
        BODY, TRACK = "\u2592", "\u2588"
        _PARTIAL = "         "  # no eighth-blocks; meters fill whole cells
    else:
        Q_TL, Q_TR, Q_BL, Q_BR = "\u2598", "\u259d", "\u2596", "\u2597"
        FULL, HALF_UP, HALF_DOWN = "\u2588", "\u2580", "\u2584"
        CAP_LEFT, CAP_RIGHT = "\u2590", "\u258c"
        BODY, TRACK = "\u2592", "\u2588"
        _PARTIAL = " \u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"


# --------------------------------------------------------------------------
# Graphs
# --------------------------------------------------------------------------
def braille_graph(
    values: Sequence[float],
    width: int,
    height: int,
    vmax: float = 1.0,
    stops: Sequence[tuple[float, str]] | None = None,
) -> list[Text]:
    """Render a scrolling history graph.

    Newest sample sits at the right edge, exactly like btop. Each terminal
    cell holds 2 horizontal x 4 vertical dots, so the effective resolution is
    ``width * 2`` samples by ``height * 4`` levels. Colour is applied per cell
    row so tall spikes climb through the gradient into the red.
    """
    stops = stops or P.LOAD_STOPS
    if width <= 0 or height <= 0:
        return []
    if GLYPHS != "braille":
        return _column_graph(values, width, height, vmax, stops)

    columns = width * 2
    recent = list(values)[-columns:]
    samples: list[float | None] = [None] * (columns - len(recent)) + list(recent)

    total = height * 4
    heights: list[int] = []
    for value in samples:
        if value is None:
            heights.append(0)
            continue
        fraction = 0.0 if vmax <= 0 else max(0.0, min(1.0, value / vmax))
        dots = int(round(fraction * total))
        if dots == 0 and value > 0:
            dots = 1  # never let a live series vanish completely
        heights.append(dots)

    lines: list[Text] = []
    for row in range(height):
        position = 1.0 - (row / max(1, height - 1))
        style = Style(color=P.gradient(position, stops))
        chars: list[str] = []
        for x in range(width):
            code = 0
            for col in (0, 1):
                filled = heights[x * 2 + col]
                for dot_row in range(4):
                    if total - (row * 4 + dot_row) <= filled:
                        code |= _DOT[col][dot_row]
            chars.append(chr(BRAILLE_BASE + code))
        lines.append(Text("".join(chars), style=style))
    return lines


def _column_graph(
    values: Sequence[float],
    width: int,
    height: int,
    vmax: float,
    stops: Sequence[tuple[float, str]],
) -> list[Text]:
    """Solid-column fallback for fonts without braille.

    One sample per cell instead of two, and half-cell precision from the
    upper-half block, so a 10-row graph still resolves 20 levels.
    """
    recent = list(values)[-width:]
    samples: list[float | None] = [None] * (width - len(recent)) + list(recent)

    halves: list[int] = []
    for value in samples:
        if value is None:
            halves.append(0)
            continue
        fraction = 0.0 if vmax <= 0 else max(0.0, min(1.0, value / vmax))
        if HALF_DOWN == FULL:
            # No half block to land on, so work in whole cells.
            steps = int(round(fraction * height)) * 2
        else:
            steps = int(round(fraction * height * 2))
        if steps == 0 and value > 0:
            steps = 2 if HALF_DOWN == FULL else 1
        halves.append(steps)

    lines: list[Text] = []
    for row in range(height):
        position = 1.0 - (row / max(1, height - 1))
        style = Style(color=P.gradient(position, stops))
        line = Text()
        # Rows below the curve are solid; the row the curve lands in gets a
        # half block when the value sits on an odd half-step.
        floor = (height - row) * 2
        body = BODY
        for filled in halves:
            if filled > floor + 1:
                line.append(body, style=style)      # well below the curve
            elif filled >= floor:
                line.append(FULL, style=style)      # the curve lands here
            elif filled == floor - 1:
                line.append(HALF_DOWN, style=style)
            else:
                line.append(" ")
        lines.append(line)
    return lines


def sparkline(values: Sequence[float], width: int, vmax: float = 1.0,
              stops: Sequence[tuple[float, str]] | None = None) -> Text:
    """Single-row history strip for tight spaces."""
    stops = stops or P.LOAD_STOPS
    blocks = " ▁▂▃▄▅▆▇█" if GLYPHS == "braille" else " " + FULL * 8
    recent = list(values)[-width:]
    recent = [0.0] * (width - len(recent)) + recent
    text = Text()
    for value in recent:
        fraction = 0.0 if vmax <= 0 else max(0.0, min(1.0, value / vmax))
        text.append(blocks[int(round(fraction * 8))], style=P.gradient(fraction, stops))
    return text


# --------------------------------------------------------------------------
# Meters
# --------------------------------------------------------------------------
def meter(
    fraction: float,
    width: int,
    stops: Sequence[tuple[float, str]] | None = None,
    track: str | None = None,
) -> Text:
    """A horizontal bar whose colour follows the fill, with 1/8 cell precision."""
    stops = stops or P.LOAD_STOPS
    track = track or P.DIM
    if width <= 0:
        return Text()
    fraction = max(0.0, min(1.0, fraction))
    exact = fraction * width
    whole = int(exact)
    remainder = int((exact - whole) * 8)
    if whole == 0 and fraction > 0 and _PARTIAL[1] == " ":
        whole = 1   # without eighth-blocks, round a live value up to one cell

    text = Text()
    for cell in range(whole):
        text.append(FULL, style=P.gradient((cell + 1) / width, stops))
    used = whole
    if remainder and used < width and GLYPHS == "braille":
        text.append(_PARTIAL[remainder], style=P.gradient((used + 1) / width, stops))
        used += 1
    if used < width:
        text.append(TRACK * (width - used), style=track)
    return text


def segmented_meter(fraction: float, width: int, segment: int = 3,
                    stops: Sequence[tuple[float, str]] | None = None,
                    track: str | None = None) -> Text:
    """Blocky LCARS bar: solid segments separated by single-cell gaps."""
    stops = stops or P.LOAD_STOPS
    track = track or P.DIM
    if width <= 0:
        return Text()
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    text = Text()
    for cell in range(width):
        if (cell + 1) % (segment + 1) == 0:
            text.append(" ")
            continue
        if cell < filled:
            text.append(FULL, style=P.gradient((cell + 1) / width, stops))
        else:
            text.append(TRACK, style=track)
    return text


# --------------------------------------------------------------------------
# LCARS chrome
# --------------------------------------------------------------------------
def pill(label: str, width: int, colour: str | None = None, height: int = 2,
         align: str = "right", text_colour: str | None = None,
         active: bool = False) -> list[Text]:
    """A chamfered LCARS block button.

    Height 1 renders as a single capsule; height 2 puts a solid cap row above
    a labelled row, which is what the real interface does for its nav stack.
    """
    colour = colour or P.ORANGE
    text_colour = text_colour or P.BLACK
    width = max(4, width)
    inner = width - 2
    body = label.upper()[:inner]
    padded = body.rjust(inner) if align == "right" else (
        body.ljust(inner) if align == "left" else body.center(inner))
    if active:
        colour = P.shade(colour, 1.35)

    label_row = Text()
    label_row.append(Q_TR if height > 1 else Q_BR, style=colour)
    label_row.append(padded, style=Style(color=text_colour, bgcolor=colour, bold=True))
    label_row.append(Q_TL if height > 1 else Q_BL, style=colour)

    if height == 1:
        return [label_row]

    cap = Text()
    cap.append(Q_BR, style=colour)
    cap.append(FULL * inner, style=colour)
    cap.append(Q_BL, style=colour)

    rows = [cap]
    rows.extend([Text(FULL * width, style=colour) for _ in range(height - 2)])
    rows.append(label_row)
    return rows


def block(width: int, height: int, colour: str, chamfer_top: bool = True,
          chamfer_bottom: bool = True) -> list[Text]:
    """A plain decorative LCARS block."""
    width = max(2, width)
    rows: list[Text] = []
    for index in range(height):
        row = Text()
        first = index == 0 and chamfer_top
        last = index == height - 1 and chamfer_bottom
        left = Q_BR if first else (Q_TR if last else FULL)
        right = Q_BL if first else (Q_TL if last else FULL)
        row.append(left, style=colour)
        row.append(FULL * (width - 2), style=colour)
        row.append(right, style=colour)
        rows.append(row)
    return rows


def panel_bar(label: str, width: int, colour: str | None = None,
              code: str = "", value: Text | None = None) -> Text:
    """Header strip for a content panel: rounded caps, black caps-lock label."""
    colour = colour or P.ORANGE
    width = max(8, width)
    bar = Text()
    bar.append(CAP_LEFT, style=colour)
    inner = width - 2

    left = f" {label.upper()} "
    right = f" {code} " if code else " "
    body = Text()
    body.append(left, style=Style(color=P.BLACK, bgcolor=colour, bold=True))
    remaining = inner - len(left) - len(right)
    if value is not None and remaining > value.cell_len + 2:
        gap = remaining - value.cell_len - 1
        body.append(" " * gap, style=Style(bgcolor=P.BLACK))
        body.append(value)
        body.append(" ", style=Style(bgcolor=P.BLACK))
    elif remaining > 0:
        body.append(" " * remaining, style=Style(bgcolor=P.BLACK))
    body.append(right, style=Style(color=P.BLACK, bgcolor=colour, bold=True))

    bar.append(body)
    bar.append(CAP_RIGHT, style=colour)
    return bar


def elbow_rows(width: int, arm: int, height: int, colour: str | None = None,
               corner: str = "top-left") -> list[Text]:
    """An LCARS elbow: a thick vertical arm sweeping into a thin horizontal bar.

    Returns ``height`` rows of ``width`` cells. The arm occupies the left
    ``arm`` columns for the full height; the horizontal bar is one row thick
    at the top (or bottom) and runs to the right edge. Corners are chamfered
    with quadrant blocks and an inside fillet is placed where the two meet.
    """
    colour = colour or P.ORANGE
    rows: list[Text] = []
    bar_row = 0 if corner == "top-left" else height - 1
    for index in range(height):
        row = Text()
        arm_chars = FULL * arm
        if index == 0 and corner == "top-left":
            arm_chars = Q_BR + FULL * (arm - 1)
        elif index == height - 1 and corner == "bottom-left":
            arm_chars = Q_TR + FULL * (arm - 1)
        row.append(arm_chars, style=colour)
        if index == bar_row:
            row.append(FULL * max(0, width - arm - 1), style=colour)
            row.append(CAP_RIGHT, style=colour)
        else:
            fillet = (Q_TL if corner == "top-left" else Q_BL) if index == (
                bar_row + 1 if corner == "top-left" else bar_row - 1) else " "
            row.append(fillet, style=colour)
            row.append(" " * max(0, width - arm - 1))
        rows.append(row)
    return rows


def segment_strip(width: int, colours: Iterable[str] | None = None,
                  seed: int = 0) -> Text:
    """The broken-up bar of coloured segments LCARS uses to fill dead space."""
    colours = list(colours or P.ROTATION)
    text = Text()
    remaining = width
    lengths = (9, 4, 13, 6, 3, 17, 7, 5, 11)
    index = seed
    while remaining > 0:
        size = min(remaining, lengths[index % len(lengths)])
        if remaining - size < 3:
            size = remaining
        text.append(FULL * max(1, size - 1), style=colours[index % len(colours)])
        if size > 1 and remaining - size > 0:
            text.append(" ")
        remaining -= size
        index += 1
    return text


def lcars_code(*parts: object) -> str:
    """LCARS-style reference number, e.g. ``47-1701-D``."""
    return "-".join(str(p) for p in parts)
