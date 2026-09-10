"""Modal screens: help, log tail, pod detail, delete confirmation."""

from __future__ import annotations

import json

from rich.console import Group, RenderResult
from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import RichLog, Static

from . import glyphs as G
from . import palette as P
from .cluster import Pod, humanize_age, humanize_bytes, humanize_cpu

MODAL_CSS = """
#frame { width: 92%; height: 88%; background: $lcars-black; }
#rail { width: 2; }
#frame-inner { width: 1fr; padding-left: 1; }
#frame-bar { height: 1; }
#frame-body { height: 1fr; }
#frame-foot { height: 1; }
#frame-close { height: 1; }
RichLog {
    background: $lcars-black; color: $lcars-tan; height: 1fr;
    scrollbar-background: #16120A; scrollbar-color: $lcars-orange;
    scrollbar-size-vertical: 1;
}
"""


class SideRail(Widget):
    """The stack of blocks down a panel's left edge."""

    DEFAULT_CSS = "SideRail { width: 2; }"
    RUN = (5, 2, 8, 3, 6, 11, 2, 4, 7)

    def __init__(self, colour: str = P.ORANGE, **kwargs) -> None:
        super().__init__(**kwargs)
        self.colour = colour

    def on_resize(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        height = max(1, self.size.height)
        colours = (self.colour, P.TAN, P.LILAC, P.PERIWINKLE, P.BUTTERSCOTCH)
        rows: list[Text] = []
        index = 0
        while len(rows) < height:
            rows.extend(G.block(2, self.RUN[index % len(self.RUN)],
                                colours[index % len(colours)]))
            rows.append(Text("  "))
            index += 1
        return Group(*rows[:height])


class ClosingBar(Widget):
    """The bar that caps the bottom of a panel."""

    DEFAULT_CSS = "ClosingBar { height: 1; }"

    def __init__(self, colour: str = P.ORANGE, **kwargs) -> None:
        super().__init__(**kwargs)
        self.colour = colour

    def on_resize(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        width = max(4, self.size.width)
        bar = Text()
        bar.append(G.CAP_LEFT, style=self.colour)
        bar.append(G.FULL * (width - 2), style=self.colour)
        bar.append(G.CAP_RIGHT, style=self.colour)
        return bar


class FrameBar(Widget):
    """LCARS panel bar that tracks the modal's width."""

    DEFAULT_CSS = "FrameBar { height: 1; }"

    def __init__(self, label: str, code: str, colour: str = P.ORANGE, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label, self.code, self.colour = label, code, colour
        self.value = Text()

    def set_value(self, value: Text) -> None:
        self.value = value
        self.refresh()

    def on_resize(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        return G.panel_bar(self.label, max(12, self.size.width), self.colour,
                           self.code, self.value)


def key_hint(*pairs: tuple[str, str]) -> Text:
    text = Text()
    for key, label in pairs:
        text.append(f" {key} ", style=Style(color=P.BLACK, bgcolor=P.SUNFLOWER, bold=True))
        text.append(f" {label}   ", style=P.GREY)
    return text


class LcarsModal(ModalScreen):
    """Shared frame: bar on top, body, hint strip at the bottom."""

    CSS = MODAL_CSS
    BINDINGS = [Binding("escape", "dismiss_screen", "Close", show=False),
                Binding("q", "dismiss_screen", "Close", show=False)]

    panel_title = "PANEL"
    code = "00-000"
    colour = P.ORANGE
    hints: tuple[tuple[str, str], ...] = (("ESC", "CLOSE"),)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # A screen's CSS is scoped to its children, so it styles itself inline.
        self.styles.align_horizontal = "center"
        self.styles.align_vertical = "middle"
        self.styles.background = (Color(0, 0, 0, 0.72)
                                  if P.MODE == "colour" else Color(0, 0, 0))

    def compose(self) -> ComposeResult:
        with Horizontal(id="frame"):
            yield SideRail(self.colour, id="rail")
            with Vertical(id="frame-inner"):
                yield FrameBar(self.panel_title, self.code, self.colour, id="frame-bar")
                yield from self.compose_body()
                yield Static(key_hint(*self.hints), id="frame-foot")
                yield ClosingBar(self.colour, id="frame-close")

    def compose_body(self) -> ComposeResult:
        yield Static()

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------
class HelpScreen(LcarsModal):
    panel_title = "OPERATIONS MANUAL"
    code = "01-ALPHA"
    colour = P.PERIWINKLE

    SECTIONS = (
        ("VIEWS", (
            ("1", "show or hide the cluster graphs"),
            ("2 / 3 / 4 / 5", "pods · nodes · events · deployments"),
            ("TAB", "cycle through the views"),
        )),
        ("SCOPE", (
            ("n", "step through namespaces"),
            ("a", "all namespaces"),
            ("/ or f", "filter by name, namespace, node or status"),
            ("ESC", "clear the filter"),
        )),
        ("POD LIST", (
            ("< / >", "move the sort column"),
            ("r", "reverse the sort order"),
            ("click header", "sort by that column"),
            ("↑ ↓ PgUp PgDn", "move the cursor"),
        )),
        ("POD ACTIONS", (
            ("l", "tail the container log"),
            ("d", "pod detail and manifest"),
            ("x or DEL", "delete the pod, with confirmation"),
        )),
        ("SCANNING", (
            ("SPACE", "hold and resume polling"),
            ("+ / -", "slower or faster scan interval"),
            ("CTRL+R", "scan once, now"),
        )),
        ("READING THE PANELS", (
            ("graphs", "cluster-wide use, newest sample on the right"),
            ("side meters", "one per node, busiest at the top"),
            ("CPU% / MEM%", "share of the pod's limit, or of its node when unset"),
        )),
    )

    def compose_body(self) -> ComposeResult:
        body = Text()
        for heading, rows in self.SECTIONS:
            body.append(f"\n {heading}\n", style=Style(color=P.ORANGE, bold=True))
            for key, description in rows:
                body.append(f"   {key:>14}  ", style=P.SUNFLOWER)
                body.append(f"{description}\n", style=P.TAN)
        body.append("\n Colour tracks load: ", style=P.GREY)
        for step in range(0, 11):
            body.append("█", style=P.gradient(step / 10))
        body.append("  quiet to saturated.\n", style=P.GREY)
        with VerticalScroll(id="frame-body"):
            yield Static(body)


# --------------------------------------------------------------------------
class ConfirmScreen(LcarsModal):
    """Delete confirmation. Nothing is destroyed without passing through here."""

    CSS = MODAL_CSS + """
    #frame { width: 72; height: 13; }
    """
    BINDINGS = [
        Binding("escape", "no", "Cancel", show=False),
        Binding("n", "no", "Cancel", show=False),
        Binding("q", "no", "Cancel", show=False),
        Binding("y", "yes", "Delete", show=False),
        Binding("enter", "yes", "Delete", show=False),
    ]
    panel_title = "CONFIRM DELETE"
    code = "99-DEL"
    colour = P.MARS
    hints = (("Y", "DELETE"), ("N", "CANCEL"))

    def __init__(self, pod: Pod) -> None:
        super().__init__()
        self.pod = pod

    def compose_body(self) -> ComposeResult:
        body = Text()
        body.append("\n Delete this pod?\n\n", style=Style(color=P.TAN, bold=True))
        body.append("   ")
        body.append(self.pod.namespace, style=P.PERIWINKLE)
        body.append(" / ", style=P.GREY)
        body.append(self.pod.name, style=P.SUNFLOWER)
        body.append("\n\n   ")
        if self.pod.owner:
            body.append(f"{self.pod.owner} will recreate it.\n", style=P.GREY)
        else:
            body.append("Nothing owns it — it will not come back.\n", style=P.MARS)
        yield Static(body, id="frame-body")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

    def action_dismiss_screen(self) -> None:
        self.dismiss(False)


# --------------------------------------------------------------------------
class DetailScreen(LcarsModal):
    """Pod summary plus the manifest, for when the table isn't enough."""

    code = "07-DET"
    colour = P.LILAC
    hints = (("ESC", "CLOSE"), ("m", "TOGGLE MANIFEST"))
    BINDINGS = LcarsModal.BINDINGS + [Binding("m", "toggle_manifest", "Manifest",
                                             show=False)]

    def __init__(self, source, pod: Pod) -> None:
        super().__init__()
        self.source = source
        self.pod = pod
        self.panel_title = f"POD · {pod.name}"[:46]
        self.manifest: dict | None = None
        self.show_manifest = False

    def compose_body(self) -> ComposeResult:
        with VerticalScroll(id="frame-body"):
            yield Static(self._summary(), id="detail")

    def on_mount(self) -> None:
        self._load()

    @work(thread=True)
    def _load(self) -> None:
        try:
            manifest = self.source.describe_pod(self.pod.namespace, self.pod.name)
        except Exception as error:  # noqa: BLE001
            manifest = {"error": f"{error.__class__.__name__}: {error}"}
        self.app.call_from_thread(self._store, manifest)

    def _store(self, manifest: dict) -> None:
        self.manifest = manifest
        self.query_one("#detail", Static).update(self._summary())

    def action_toggle_manifest(self) -> None:
        self.show_manifest = not self.show_manifest
        self.query_one("#detail", Static).update(self._summary())

    def _summary(self):
        pod = self.pod
        text = Text()

        def row(label: str, value: str, colour: str = P.TAN) -> None:
            text.append(f"  {label:>12}  ", style=P.GREY)
            text.append(f"{value}\n", style=colour)

        text.append("\n")
        row("NAMESPACE", pod.namespace, P.PERIWINKLE)
        row("NAME", pod.name, P.SUNFLOWER)
        row("STATUS", pod.status, P.status_colour(pod.status))
        row("READY", pod.ready, P.ANAKIWA)
        row("RESTARTS", str(pod.restarts), P.MARS if pod.restarts else P.TAN)
        row("NODE", pod.node or "unscheduled", P.TAN)
        row("POD IP", pod.ip or "—")
        row("QOS", pod.qos or "—")
        row("OWNER", pod.owner or "none")
        row("AGE", humanize_age(pod.created))
        row("CONTAINERS", ", ".join(pod.containers) or "—")
        row("CPU", f"{humanize_cpu(pod.cpu)} used · "
                   f"{humanize_cpu(pod.cpu_request)} requested · "
                   f"{humanize_cpu(pod.cpu_limit) if pod.cpu_limit else 'no'} limit")
        row("MEMORY", f"{humanize_bytes(pod.mem)} used · "
                      f"{humanize_bytes(pod.mem_request)} requested · "
                      f"{humanize_bytes(pod.mem_limit) if pod.mem_limit else 'no'} limit")
        if pod.message:
            text.append("\n")
            row("MESSAGE", pod.message, P.MARS)

        if self.show_manifest:
            text.append("\n  MANIFEST\n", style=Style(color=P.ORANGE, bold=True))
            if self.manifest is None:
                text.append("  reading…\n", style=P.GREY)
            else:
                dump = json.dumps(self.manifest, indent=2, default=str)
                text.append("\n".join(f"  {line}" for line in dump.splitlines()),
                            style=P.GREY)
        else:
            text.append("\n  Press ", style=P.GREY)
            text.append("m", style=P.SUNFLOWER)
            text.append(" for the full manifest.\n", style=P.GREY)
        return text


# --------------------------------------------------------------------------
class LogScreen(LcarsModal):
    """Live tail. Re-reads the tail on a timer and appends only what's new."""

    code = "12-LOG"
    colour = P.ANAKIWA
    hints = (("ESC", "CLOSE"), ("c", "NEXT CONTAINER"), ("p", "PREVIOUS INSTANCE"),
             ("SPACE", "HOLD"))
    BINDINGS = LcarsModal.BINDINGS + [
        Binding("c", "next_container", "Container", show=False),
        Binding("p", "toggle_previous", "Previous", show=False),
        Binding("space", "toggle_hold", "Hold", show=False),
    ]

    def __init__(self, source, pod: Pod) -> None:
        super().__init__()
        self.source = source
        self.pod = pod
        self.containers = list(pod.containers) or [""]
        self.index = 0
        self.previous = False
        self.held = False
        self.lines: list[str] = []
        self.panel_title = f"LOG · {pod.name}"[:46]
        self._timer = None

    def compose_body(self) -> ComposeResult:
        yield RichLog(id="frame-body", highlight=False, markup=False, wrap=True,
                      max_lines=4000, auto_scroll=True)

    def on_mount(self) -> None:
        self._update_bar()
        self._fetch(reset=True)
        self._timer = self.set_interval(1.5, self._poll)

    def _update_bar(self) -> None:
        value = Text()
        value.append(self.containers[self.index] or "default", style=P.SUNFLOWER)
        if self.previous:
            value.append("  PREVIOUS", style=P.MARS)
        if self.held:
            value.append("  HELD", style=P.LILAC)
        self.query_one(FrameBar).set_value(value)

    def _poll(self) -> None:
        if not self.held:
            self._fetch()

    @work(thread=True, exclusive=True, group="logs")
    def _fetch(self, reset: bool = False) -> None:
        container = self.containers[self.index] or None
        try:
            raw = self.source.pod_logs(self.pod.namespace, self.pod.name,
                                       container=container, tail=500,
                                       previous=self.previous)
            lines = raw.splitlines()
        except Exception as error:  # noqa: BLE001
            lines = [f"[log unavailable] {error.__class__.__name__}: "
                     f"{str(error).splitlines()[0][:120]}"]
            reset = True
        self.app.call_from_thread(self._append, lines, reset)

    def _append(self, lines: list[str], reset: bool) -> None:
        log = self.query_one(RichLog)
        if reset:
            log.clear()
            self.lines = []
        if not self.lines:
            fresh = lines
        else:
            anchor = self.lines[-1]
            try:
                position = len(lines) - 1 - lines[::-1].index(anchor)
                fresh = lines[position + 1:]
            except ValueError:
                fresh = lines
        for line in fresh:
            log.write(Text(line, style=P.TAN))
        self.lines = lines[-500:]

    def action_next_container(self) -> None:
        if len(self.containers) > 1:
            self.index = (self.index + 1) % len(self.containers)
            self._update_bar()
            self._fetch(reset=True)

    def action_toggle_previous(self) -> None:
        self.previous = not self.previous
        self._update_bar()
        self._fetch(reset=True)

    def action_toggle_hold(self) -> None:
        self.held = not self.held
        self._update_bar()
