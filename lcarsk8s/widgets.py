"""The LCARS chrome, built as Textual widgets."""

from __future__ import annotations

from collections import deque
from typing import Sequence

from rich.console import Group, RenderResult
from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from . import glyphs as G
from . import palette as P
from .cluster import Node, Snapshot, humanize_bytes, humanize_cpu, stardate

ARM = 20  # width of the vertical elbow arm / sidebar


def _pad(text: Text, width: int) -> Text:
    if text.cell_len < width:
        text.append(" " * (width - text.cell_len))
    return text


class LcarsHeader(Widget):
    """Top-left elbow sweeping into the title bar."""

    DEFAULT_CSS = "LcarsHeader { height: 3; }"

    title_text = reactive("KUBERNETES OPERATIONS")
    context = reactive("-")
    version = reactive("-")
    detail = reactive("")

    def on_resize(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        width = max(ARM + 8, self.size.width)
        expanded = self.size.height >= 5
        rows: list[Text] = []

        top = Text()
        top.append(G.FULL * ARM, style=P.BUTTERSCOTCH)
        top.append(G.FULL * max(1, width - ARM - 1), style=P.ORANGE)
        top.append(G.CAP_RIGHT, style=P.ORANGE)
        rows.append(_pad(top, width))

        title = Text()
        title.append(G.FULL * ARM, style=P.BUTTERSCOTCH)
        title.append(G.Q_TL, style=P.BUTTERSCOTCH)
        title.append(" ")
        title.append(self.title_text.upper(), style=Style(color=P.ORANGE, bold=True))
        right = Text()
        right.append(f"{self.context} ", style=P.TAN)
        right.append("· ", style=P.GREY)
        right.append(self.version, style=P.ANAKIWA)
        gap = width - title.cell_len - right.cell_len - 1
        if gap > 0:
            title.append(" " * gap)
            title.append(right)
        rows.append(_pad(title, width))

        identity = Text()
        identity.append(G.Q_TR, style=P.BUTTERSCOTCH)
        identity.append(f"{G.lcars_code(47, 1701)} ".rjust(ARM - 1),
                        style=Style(color=P.BLACK, bgcolor=P.BUTTERSCOTCH, bold=True))
        identity.append("  ")
        identity.append(self.detail, style=P.GREY)
        trailer = Text(f"STARDATE {stardate()}", style=P.LILAC)
        gap = width - identity.cell_len - trailer.cell_len - 1
        if gap > 0:
            identity.append(" " * gap)
            identity.append(trailer)
        rows.append(_pad(identity, width))

        if expanded:
            signal = Text()
            signal.append(G.FULL * 7, style=P.BUTTERSCOTCH)
            signal.append(" ")
            signal.append(G.FULL * (ARM - 8), style=P.LILAC)
            signal.append("  ")
            signal.append(G.segment_strip(max(1, width - ARM - 2),
                                          (P.PERIWINKLE, P.TAN, P.ORANGE,
                                           P.LILAC, P.BUTTERSCOTCH), seed=5))
            rows.append(_pad(signal, width))

            channel = Text()
            channel.append(G.FULL * ARM, style=P.LILAC)
            channel.append(G.Q_BL, style=P.LILAC)
            channel.append("  PRIMARY OPERATIONS CHANNEL", style=P.GREY)
            links = {"console": "CONSOLE LINK 16C", "kmscon": "KMSCON LINK 256C",
                     "fbterm": "FBTERM LINK 256C", "colour": "FULL-SPECTRUM LINK"}
            mode = Text(links[P.MODE], style=P.PERIWINKLE)
            gap = width - channel.cell_len - mode.cell_len - 1
            if gap > 0:
                channel.append(" " * gap)
                channel.append(mode)
            rows.append(_pad(channel, width))
        return Group(*rows)


class LcarsFooter(Widget):
    """Bottom elbow carrying the key legend and the last action's result."""

    DEFAULT_CSS = "LcarsFooter { height: 2; }"

    status = reactive("STANDING BY")
    status_colour = reactive(P.ORANGE)
    keys = reactive("")

    def on_resize(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        width = max(ARM + 8, self.size.width)
        expanded = self.size.height >= 3

        legend = Text()
        legend.append(G.FULL * ARM, style=P.LILAC)
        legend.append(G.Q_BL, style=P.LILAC)
        legend.append(" ")
        for chunk in self.keys.split("  "):
            if not chunk:
                continue
            key, _, label = chunk.partition(":")
            legend.append(f"{key}", style=Style(color=P.SUNFLOWER, bold=True))
            legend.append(f" {label}  ", style=P.GREY)
        legend.truncate(width)

        rows = [_pad(legend, width)]
        if expanded:
            signal = Text()
            signal.append(G.FULL * 8, style=P.LILAC)
            signal.append(" ")
            signal.append(G.FULL * (ARM - 9), style=P.PERIWINKLE)
            signal.append("  ")
            signal.append(G.segment_strip(max(1, width - ARM - 2),
                                          (P.LILAC, P.TAN, P.PERIWINKLE,
                                           P.BUTTERSCOTCH), seed=2))
            rows.append(_pad(signal, width))

        bar = Text()
        bar.append(G.Q_TR, style=P.LILAC)
        bar.append(G.FULL * (ARM - 1), style=P.LILAC)
        message = f" {self.status.upper()} "
        body_width = width - ARM - 1
        text = message.rjust(max(0, body_width))[-max(0, body_width):]
        bar.append(text, style=Style(color=P.BLACK, bgcolor=self.status_colour, bold=True))
        bar.append(G.CAP_RIGHT, style=self.status_colour)
        rows.append(_pad(bar, width))
        return Group(*rows)


class LcarsSidebar(Widget):
    """The stack of LCARS nav blocks down the left edge.

    Rows are click-mapped, so the whole thing works with the mouse as well as
    the keyboard.
    """

    DEFAULT_CSS = f"LcarsSidebar {{ width: {ARM}; }}"

    view = reactive("pods")
    namespace = reactive("")
    namespaces = reactive(tuple())
    paused = reactive(False)
    interval = reactive(2.0)

    NAV = (("pods", "02  PODS", P.ORANGE),
           ("nodes", "03  NODES", P.LILAC),
           ("events", "04  EVENTS", P.TAN),
           ("deployments", "05  DEPLOYMENTS", P.PERIWINKLE))

    class Selected(Message):
        def __init__(self, kind: str, value: str) -> None:
            self.kind = kind
            self.value = value
            super().__init__()

    def __init__(self, side: str = "left") -> None:
        super().__init__()
        self.side = side
        self._hitmap: dict[int, tuple[str, str]] = {}

    def on_resize(self) -> None:
        self.refresh()

    def on_click(self, event) -> None:
        target = self._hitmap.get(event.y)
        if target:
            self.post_message(self.Selected(*target))

    def render(self) -> RenderResult:
        width, height = ARM, max(12, self.size.height)
        rows: list[Text] = []
        hits: dict[int, tuple[str, str]] = {}

        rows.append(Text(" " * width))
        align = "right" if self.side == "left" else "left"
        for key, label, colour in self.NAV:
            block = G.pill(label, width, colour, height=2, align=align,
                           active=(self.view == key))
            for offset in range(len(block)):
                hits[len(rows) + offset] = ("view", key)
            rows.extend(block)
            rows.append(Text(" " * width))

        rows.extend(G.pill("NAMESPACE", width, P.BUTTERSCOTCH, height=1,
                           align="center"))
        rows.append(Text(" " * width))

        entries = [("", "ALL")] + [(ns, ns) for ns in self.namespaces]
        remaining = height - len(rows) - 6
        for value, label in entries[:max(0, remaining)]:
            selected = self.namespace == value
            colour = P.ANAKIWA if selected else P.GREY
            row = G.pill(label, width, colour, height=1, align=align,
                         text_colour=P.BLACK if selected else "#0A0A12")[0]
            hits[len(rows)] = ("namespace", value)
            rows.append(row)
        if len(entries) > max(0, remaining):
            hidden = len(entries) - max(0, remaining)
            message = f"+{hidden} MORE"
            rows.append(Text(message.rjust(width) if self.side == "left"
                             else message.ljust(width), style=P.GREY))

        while len(rows) < height - 4:
            rows.append(Text(" " * width))

        cadence = "HOLD" if self.paused else f"{self.interval:g}S"
        footer_colour = P.MARS if self.paused else P.LILAC
        rows.append(Text(" " * width))
        block = G.pill(f"SCAN {cadence}", width, footer_colour, height=1, align="center")
        hits[len(rows)] = ("pause", "")
        rows.extend(block)
        rows.append(Text(" " * width))
        rows.append(G.segment_strip(width, (P.ORANGE, P.TAN, P.LILAC), seed=3))

        self._hitmap = hits
        return Group(*rows[:height])


class LoadPanel(Widget):
    """btop's CPU box, re-pointed at a cluster.

    A scrolling braille history graph on the left, one meter per node on the
    right where btop would put per-core meters.
    """

    DEFAULT_CSS = "LoadPanel { height: 1fr; }"

    def __init__(self, label: str, code: str, colour: str,
                 stops: Sequence[tuple[float, str]], history: int = 600,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.code = code
        self.colour = colour
        self.stops = stops
        self.history: deque[float] = deque(maxlen=history)
        self.fraction = 0.0
        self.headline = ""
        self.rows: list[tuple[str, float, str]] = []

    def update(self, fraction: float, headline: str,
               rows: Sequence[tuple[str, float, str]]) -> None:
        self.history.append(fraction)
        self.fraction = fraction
        self.headline = headline
        self.rows = list(rows)
        self.refresh()

    def render(self) -> RenderResult:
        width = max(24, self.size.width)
        height = max(4, self.size.height)

        value = Text()
        value.append(f"{self.fraction * 100:5.1f}%",
                     style=Style(color=P.gradient(self.fraction, self.stops), bold=True))
        value.append(f"  {self.headline}", style=P.TAN)
        bar = G.panel_bar(self.label, width, self.colour, self.code, value)

        graph_height = height - 1
        label_width = min(12, max(4, max((len(r[0]) for r in self.rows), default=4)))
        meter_width = 0
        if width >= 56 and self.rows:
            meter_width = min(label_width + 18, max(18, width // 3))
        graph_width = width - meter_width

        graph = G.braille_graph(self.history, graph_width, graph_height,
                                vmax=1.0, stops=self.stops)

        # One meter per node. If they don't all fit, the busiest win and the
        # last line says how many were left out.
        visible = self.rows
        overflow = 0
        if len(visible) > graph_height:
            visible = self.rows[:graph_height - 1]
            overflow = len(self.rows) - len(visible)

        lines: list[Text] = [bar]
        for index in range(graph_height):
            line = Text()
            line.append(graph[index] if index < len(graph) else Text())
            if meter_width:
                if index < len(visible):
                    line.append(self._meter_row(visible[index], meter_width, label_width))
                elif overflow and index == len(visible):
                    line.append(f" +{overflow} MORE".ljust(meter_width), style=P.GREY)
            lines.append(line)
        return Group(*lines)

    def _meter_row(self, entry: tuple[str, float, str], width: int,
                   label_width: int) -> Text:
        name, fraction, suffix = entry
        row = Text()
        row.append(" ")
        row.append(name[:label_width].ljust(label_width + 1), style=P.TAN)
        gauge = width - label_width - len(suffix) - 4
        row.append(G.meter(fraction, max(4, gauge), self.stops))
        row.append(f" {suffix}", style=P.gradient(fraction, self.stops))
        return row


class StatStrip(Widget):
    """One-line workload tally under the graphs."""

    DEFAULT_CSS = "StatStrip { height: 1; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.snapshot: Snapshot | None = None

    def update_snapshot(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.refresh()

    def render(self) -> RenderResult:
        if self.snapshot is None:
            return Text("AWAITING TELEMETRY", style=P.GREY)
        snap = self.snapshot
        counts = snap.counts()
        ready_nodes = sum(1 for n in snap.nodes if n.ready)
        restarts = sum(p.restarts for p in snap.pods)

        text = Text()

        def cell(label: str, value: str, colour: str) -> None:
            text.append(f" {label} ", style=Style(color=P.BLACK, bgcolor=colour, bold=True))
            text.append(f" {value}   ", style=colour)

        cell("NODES", f"{ready_nodes}/{len(snap.nodes)}", P.ORANGE)
        cell("PODS", str(len(snap.pods)), P.TAN)
        cell("RUN", str(counts["running"]), P.ANAKIWA)
        cell("PEND", str(counts["pending"]), P.SUNFLOWER)
        cell("FAIL", str(counts["failed"]), P.MARS if counts["failed"] else P.GREY)
        cell("RESTARTS", str(restarts), P.LILAC)
        cell("CPU", f"{humanize_cpu(snap.cpu_used)}/{humanize_cpu(snap.cpu_capacity)}", P.BUTTERSCOTCH)
        cell("MEM", f"{humanize_bytes(snap.mem_used)}/{humanize_bytes(snap.mem_capacity)}", P.PERIWINKLE)
        if not snap.metrics_available:
            cell("NO METRICS-SERVER — SHOWING REQUESTS", "", P.MARS)
        return text


def distinguishing_names(names: Sequence[str]) -> dict[str, str]:
    """Strip the shared prefix from a set of node names.

    Node names in a cluster usually differ only at the tail
    (``ip-10-0-1-12`` / ``ip-10-0-1-13``), so the shared head is the part
    worth dropping when space is tight.
    """
    unique = [n for n in names if n]
    if len(unique) < 2:
        return {name: name for name in names}
    prefix = unique[0]
    for name in unique[1:]:
        while prefix and not name.startswith(prefix):
            prefix = prefix[:-1]
    prefix = prefix.rstrip("-.")
    if len(prefix) < 3 or any(len(name) - len(prefix) < 2 for name in unique):
        return {name: name for name in names}
    cut = len(prefix)
    return {name: name[cut:].lstrip("-.") or name for name in names}


def node_meter_rows(nodes: Sequence[Node], attribute: str) -> list[tuple[str, float, str]]:
    """Per-node meter rows for a :class:`LoadPanel`, busiest first."""
    labels = distinguishing_names([node.short_name for node in nodes])
    rows = []
    for node in sorted(nodes, key=lambda n: getattr(n, attribute), reverse=True):
        fraction = getattr(node, attribute)
        rows.append((labels[node.short_name], fraction, f"{fraction * 100:3.0f}%"))
    return rows
