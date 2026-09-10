"""The LCARS Kubernetes console."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import DataTable, Input, RichLog, Static

from . import glyphs as G
from . import palette as P
from .cluster import (ClusterError, Snapshot, humanize_age, humanize_bytes,
                      humanize_cpu)
from .screens import ConfirmScreen, DetailScreen, HelpScreen, LogScreen
from .widgets import (ARM, LcarsFooter, LcarsHeader, LcarsSidebar, LoadPanel,
                      StatStrip, node_meter_rows)

# Every palette entry is available in CSS as $lcars-<name>. P.css() turns
# console-mode ANSI names into the ansi_* spelling Textual CSS expects.
LCARS_VARIABLES = {
    **{f"lcars-{name.lower().replace('_', '-')}": P.css(value)
       for name, value in vars(P).items()
       if name.isupper() and isinstance(value, str) and value},
    "lcars-blue": P.css(P.ANAKIWA),
    "block-cursor-foreground": P.css(P.BLACK),
    "block-cursor-background": P.css(P.ORANGE),
    "input-selection-background": (f"{P.LILAC} 40%" if P.MODE == "colour"
                                   else P.css(P.LILAC)),
}

LCARS_THEME = Theme(
    name="lcars",
    primary=P.css(P.ORANGE),
    secondary=P.css(P.LILAC),
    accent=P.css(P.ANAKIWA),
    warning=P.css(P.SUNFLOWER),
    error=P.css(P.MARS),
    success=P.css(P.PERIWINKLE),
    foreground=P.css(P.TAN),
    background=P.css(P.BLACK),
    surface=P.css(P.BLACK),
    panel=P.css(P.BLACK) if P.MODE == "console" else "#12100C",
    dark=True,
    variables=dict(LCARS_VARIABLES),
)

# Sort modes for the pod table: key, column header, accessor.
POD_SORTS = (
    ("cpu", "CPU", lambda p: p.cpu),
    ("mem", "MEM", lambda p: p.mem),
    ("restarts", "RST", lambda p: p.restarts),
    ("age", "AGE", lambda p: -(p.created.timestamp() if p.created else 0)),
    ("status", "STATUS", lambda p: p.status),
    ("name", "POD", lambda p: p.name),
    ("namespace", "NS", lambda p: (p.namespace, p.name)),
    ("node", "NODE", lambda p: (p.node, p.name)),
)

KEY_LEGEND = ("2-5:view  n:ns  /:filter  <>:sort  r:rev  l:logs  d:detail  "
              "x:delete  space:hold  ?:help  q:quit")


class LcarsK8s(App):
    """btop's shape, LCARS's clothes, Kubernetes underneath."""

    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: $lcars-black; layers: base; }
    #body { height: 1fr; }
    #main { width: 1fr; }
    #meters { height: 12; }
    #meters.hidden { display: none; }
    LoadPanel { width: 1fr; }
    #cpu-panel { margin-right: 1; }
    StatStrip { margin-top: 1; }
    #table-bar { height: 1; margin-top: 1; }
    #table-host { height: 1fr; }
    DataTable {
        height: 1fr; background: $lcars-black; color: $lcars-tan;
        scrollbar-background: $lcars-black; scrollbar-color: $lcars-orange;
        scrollbar-color-hover: $lcars-sunflower;
        scrollbar-background-hover: $lcars-black;
        scrollbar-color-active: $lcars-lilac;
        scrollbar-size-vertical: 1;
    }
    DataTable.hidden { display: none; }
    DataTable > .datatable--header {
        background: $lcars-orange; color: black; text-style: bold;
    }
    DataTable > .datatable--header-hover {
        background: $lcars-sunflower; color: black; text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: $lcars-lilac; color: black; text-style: bold;
    }
    DataTable > .datatable--hover { background: $lcars-dim; }
    #filter { display: none; }
    #filter.visible { display: block; }
    Input {
        border: none; background: $lcars-dim; color: $lcars-sunflower;
        padding: 0 1; height: 1; margin-top: 1;
    }
    Input:focus { border: none; background: $lcars-dim; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("f1", "help", "Help", show=False),
        Binding("1", "toggle_meters", "Graphs", show=False),
        Binding("2", "view('pods')", "Pods", show=False),
        Binding("3", "view('nodes')", "Nodes", show=False),
        Binding("4", "view('events')", "Events", show=False),
        Binding("5", "view('deployments')", "Deployments", show=False),
        Binding("tab", "cycle_view", "Next view", show=False),
        Binding("n", "cycle_namespace", "Namespace", show=False),
        Binding("a", "all_namespaces", "All namespaces", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f", "filter", "Filter", show=False),
        Binding("comma", "sort_step(-1)", "Sort left", show=False),
        Binding("less_than_sign", "sort_step(-1)", "Sort left", show=False),
        Binding("full_stop", "sort_step(1)", "Sort right", show=False),
        Binding("greater_than_sign", "sort_step(1)", "Sort right", show=False),
        Binding("r", "reverse", "Reverse", show=False),
        Binding("l", "logs", "Logs", show=False),
        Binding("d", "detail", "Detail", show=False),
        Binding("x", "delete", "Delete", show=False),
        Binding("delete", "delete", "Delete", show=False),
        Binding("space", "pause", "Hold", show=False),
        Binding("plus", "interval(1)", "Slower", show=False),
        Binding("equals_sign", "interval(1)", "Slower", show=False),
        Binding("minus", "interval(-1)", "Faster", show=False),
        Binding("escape", "clear", "Clear", show=False),
        Binding("ctrl+r", "refresh_now", "Refresh", show=False),
    ]

    def __init__(self, source, interval: float = 2.0, namespace: str = "",
                 view: str = "pods", sidebar: str = "left") -> None:
        super().__init__()
        self.source = source
        self.interval = interval
        self.namespace = namespace
        self.view = view
        self.sidebar_side = sidebar
        self.snapshot: Snapshot | None = None
        self.filter_text = ""
        self.sort_index = 5
        self.sort_reverse = False
        self.paused = False
        self.visible_pods: list = []
        self.visible_nodes: list = []
        self.visible_deployments: list = []
        self._timer = None
        self._busy = False

    def get_css_variables(self) -> dict[str, str]:
        # App.CSS is parsed before on_mount, so the palette has to be injected
        # here as well as through the theme.
        variables = super().get_css_variables()
        variables.update(LCARS_VARIABLES)
        return variables

    # -- composition -----------------------------------------------------
    def compose(self) -> ComposeResult:
        yield LcarsHeader(id="header")
        with Horizontal(id="body"):
            if self.sidebar_side == "left":
                yield LcarsSidebar(side="left")
            with Vertical(id="main"):
                with Horizontal(id="meters"):
                    yield LoadPanel("CLUSTER CPU", "31-882", P.ORANGE, P.LOAD_STOPS,
                                    id="cpu-panel")
                    yield LoadPanel("CLUSTER MEMORY", "44-119", P.LILAC, P.MEM_STOPS,
                                    id="mem-panel")
                yield StatStrip(id="stats")
                yield Static(id="table-bar")
                with Vertical(id="table-host"):
                    yield DataTable(id="pods", zebra_stripes=False,
                                    cursor_type="row", header_height=1)
                    yield DataTable(id="nodes", classes="hidden", zebra_stripes=False,
                                    cursor_type="row", header_height=1)
                    yield DataTable(id="events", classes="hidden", zebra_stripes=False,
                                    cursor_type="row", header_height=1)
                    yield DataTable(id="deployments", classes="hidden", zebra_stripes=False,
                                    cursor_type="row", header_height=1)
                yield Input(placeholder="FILTER — name, namespace, node or status",
                            id="filter")
            if self.sidebar_side == "right":
                yield LcarsSidebar(side="right")
        yield LcarsFooter(id="footer")

    def on_mount(self) -> None:
        self.register_theme(LCARS_THEME)
        self.theme = "lcars"

        header = self.query_one(LcarsHeader)
        header.context = getattr(self.source, "context", self.source.name)
        header.detail = f"SOURCE {self.source.name.upper()}"
        self.query_one(LcarsFooter).keys = KEY_LEGEND

        self._build_columns()
        self._apply_view()
        self._schedule()
        self.refresh_data()

    def _build_columns(self) -> None:
        pods = self.query_one("#pods", DataTable)
        for label, key, width in (
            ("NS", "namespace", 16), ("POD", "name", 38), ("NODE", "node", 16),
            ("STATUS", "status", 17), ("READY", "ready", 6), ("RST", "restarts", 5),
            ("CPU", "cpu", 8), ("CPU%", "cpu_pct", 6), ("MEM", "mem", 9),
            ("MEM%", "mem_pct", 6), ("AGE", "age", 7),
        ):
            pods.add_column(Text(label, justify="left"), key=key, width=width)

        nodes = self.query_one("#nodes", DataTable)
        for label, key, width in (
            ("NODE", "name", 22), ("STATUS", "status", 10), ("ROLES", "roles", 14),
            ("CPU", "cpu", 25), ("MEMORY", "mem", 25), ("PODS", "pods", 11),
            ("VERSION", "version", 9), ("AGE", "age", 6), ("INTERNAL-IP", "ip", 15),
        ):
            nodes.add_column(Text(label), key=key, width=width)

        events = self.query_one("#events", DataTable)
        for label, key, width in (
            ("AGE", "age", 6), ("TYPE", "type", 8), ("REASON", "reason", 20),
            ("NS", "namespace", 15), ("OBJECT", "object", 30),
            ("N", "count", 4), ("MESSAGE", "message", 56),
        ):
            events.add_column(Text(label), key=key, width=width)

        deployments = self.query_one("#deployments", DataTable)
        for label, key, width in (
            ("NS", "namespace", 16), ("DEPLOYMENT", "name", 38),
            ("READY", "ready", 8), ("UP-TO-DATE", "updated", 10),
            ("AVAILABLE", "available", 10), ("UNAVAILABLE", "unavailable", 11),
            ("STRATEGY", "strategy", 14), ("AGE", "age", 7),
        ):
            deployments.add_column(Text(label), key=key, width=width)

    # -- polling ---------------------------------------------------------
    def _schedule(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_interval(self.interval, self._tick)

    def _tick(self) -> None:
        if not self.paused:
            self.refresh_data()

    def refresh_data(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._poll()

    @work(exclusive=True, thread=True, group="poll")
    def _poll(self) -> None:
        try:
            snapshot = self.source.snapshot(want_events=self.view == "events")
        except ClusterError as error:
            self.call_from_thread(self.set_status, str(error), P.MARS)
            self.call_from_thread(self._done)
            return
        except Exception as error:  # noqa: BLE001 - surfaced in the status bar
            self.call_from_thread(self.set_status,
                                  f"APISERVER: {error.__class__.__name__}", P.MARS)
            self.call_from_thread(self._done)
            return
        self.call_from_thread(self.ingest, snapshot)

    def _done(self) -> None:
        self._busy = False

    def ingest(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self._busy = False

        header = self.query_one(LcarsHeader)
        header.context = snapshot.context
        header.version = snapshot.server_version

        cpu = self.query_one("#cpu-panel", LoadPanel)
        cpu.update(snapshot.cpu_fraction,
                   f"{humanize_cpu(snapshot.cpu_used)} / {humanize_cpu(snapshot.cpu_capacity)}",
                   node_meter_rows(snapshot.nodes, "cpu_fraction"))
        mem = self.query_one("#mem-panel", LoadPanel)
        mem.update(snapshot.mem_fraction,
                   f"{humanize_bytes(snapshot.mem_used)} / {humanize_bytes(snapshot.mem_capacity)}",
                   node_meter_rows(snapshot.nodes, "mem_fraction"))

        self.query_one(StatStrip).update_snapshot(snapshot)

        sidebar = self.query_one(LcarsSidebar)
        sidebar.namespaces = tuple(sorted(snapshot.namespaces, key=str.casefold))
        sidebar.namespace = self.namespace
        sidebar.paused = self.paused
        sidebar.interval = self.interval

        self._fill_pods()
        self._fill_nodes()
        self._fill_events()
        self._fill_deployments()
        self._update_table_bar()

        if snapshot.errors and not self.paused:
            self.set_status(" · ".join(snapshot.errors)[:120], P.SUNFLOWER)

    # -- table population -------------------------------------------------
    def _matches(self, *fields: str) -> bool:
        if not self.filter_text:
            return True
        needle = self.filter_text.lower()
        return any(needle in (field or "").lower() for field in fields)

    def _node_capacity(self) -> dict[str, tuple[float, float]]:
        if not self.snapshot:
            return {}
        return {n.name: (n.cpu_capacity, n.mem_capacity) for n in self.snapshot.nodes}

    def _fill_pods(self) -> None:
        if not self.snapshot:
            return
        table = self.query_one("#pods", DataTable)
        selected = self._selected_key(table)
        offset = table.scroll_offset.y

        _, _, accessor = POD_SORTS[self.sort_index]
        pods = [p for p in self.snapshot.pods
                if (not self.namespace or p.namespace == self.namespace)
                and self._matches(p.name, p.namespace, p.node, p.status)]
        pods.sort(key=accessor, reverse=self.sort_reverse)
        self.visible_pods = pods

        capacity = self._node_capacity()
        table.clear()
        for pod in pods:
            node_cpu, node_mem = capacity.get(pod.node, (0.0, 0.0))
            cpu_ratio = (pod.cpu / pod.cpu_limit if pod.cpu_limit
                         else (pod.cpu / node_cpu if node_cpu else 0.0))
            mem_ratio = (pod.mem / pod.mem_limit if pod.mem_limit
                         else (pod.mem / node_mem if node_mem else 0.0))
            colour = P.status_colour(pod.status)
            ready_ok = pod.ready_fraction >= 1.0
            table.add_row(
                Text(pod.namespace[:16], style=P.PERIWINKLE),
                Text(pod.name[:38], style=P.TAN if pod.healthy else colour),
                Text((pod.node.split(".")[0] or "—")[:16], style=P.GREY),
                Text(pod.status[:17], style=Style(color=colour, bold=not pod.healthy)),
                Text(pod.ready, style=P.ANAKIWA if ready_ok else P.MARS),
                Text(str(pod.restarts) if pod.restarts else "·",
                     style=P.MARS if pod.restarts > 5 else
                     (P.SUNFLOWER if pod.restarts else P.GREY)),
                Text(humanize_cpu(pod.cpu) if pod.cpu else "·",
                     style=P.gradient(cpu_ratio, P.LOAD_STOPS) if pod.cpu else P.GREY),
                self._percent(cpu_ratio, pod.cpu, P.LOAD_STOPS),
                Text(humanize_bytes(pod.mem) if pod.mem else "·",
                     style=P.gradient(mem_ratio, P.MEM_STOPS) if pod.mem else P.GREY),
                self._percent(mem_ratio, pod.mem, P.MEM_STOPS),
                Text(humanize_age(pod.created), style=P.GREY),
                key=pod.key,
            )
        self._restore(table, selected, offset)

    @staticmethod
    def _percent(ratio: float, raw: float, stops) -> Text:
        if not raw:
            return Text("·", style=P.GREY)
        return Text(f"{ratio * 100:.0f}%", style=P.gradient(ratio, stops))

    def _fill_nodes(self) -> None:
        if not self.snapshot:
            return
        table = self.query_one("#nodes", DataTable)
        selected = self._selected_key(table)
        offset = table.scroll_offset.y

        nodes = sorted(
            (n for n in self.snapshot.nodes
             if self._matches(n.name, n.roles, n.condition)),
            key=lambda node: node.name.casefold(),
        )
        self.visible_nodes = nodes
        table.clear()
        for node in nodes:
            cpu = Text()
            cpu.append(G.meter(node.cpu_fraction, 18, P.LOAD_STOPS))
            cpu.append(f" {node.cpu_fraction * 100:3.0f}% ",
                       style=P.gradient(node.cpu_fraction, P.LOAD_STOPS))
            mem = Text()
            mem.append(G.meter(node.mem_fraction, 18, P.MEM_STOPS))
            mem.append(f" {node.mem_fraction * 100:3.0f}% ",
                       style=P.gradient(node.mem_fraction, P.MEM_STOPS))
            pods = Text()
            pods.append(G.meter(node.pod_fraction, 6, P.LOAD_STOPS))
            pods.append(f" {node.pod_count}/{node.pod_capacity}", style=P.TAN)
            healthy = node.ready and node.schedulable
            table.add_row(
                Text(node.name[:24], style=P.TAN),
                Text(node.condition, style=P.ANAKIWA if healthy else P.MARS),
                Text(node.roles[:15], style=P.LILAC),
                cpu, mem, pods,
                Text(node.version, style=P.GREY),
                Text(humanize_age(node.created), style=P.GREY),
                Text(node.internal_ip, style=P.GREY),
                key=node.name,
            )
        self._restore(table, selected, offset)

    def _fill_deployments(self) -> None:
        if not self.snapshot:
            return
        table = self.query_one("#deployments", DataTable)
        selected = self._selected_key(table)
        offset = table.scroll_offset.y
        deployments = sorted(
            (deployment for deployment in self.snapshot.deployments
             if (not self.namespace or deployment.namespace == self.namespace)
             and self._matches(deployment.name, deployment.namespace,
                               deployment.strategy)),
            key=lambda deployment: (deployment.name.casefold(),
                                    deployment.namespace.casefold()),
        )
        self.visible_deployments = deployments
        table.clear()
        for deployment in deployments:
            health = P.ANAKIWA if deployment.healthy else P.MARS
            table.add_row(
                Text(deployment.namespace[:16], style=P.PERIWINKLE),
                Text(deployment.name[:38], style=P.TAN),
                Text(f"{deployment.ready}/{deployment.replicas}", style=health),
                Text(str(deployment.updated), style=P.ANAKIWA),
                Text(str(deployment.available), style=P.ANAKIWA),
                Text(str(deployment.unavailable),
                     style=P.MARS if deployment.unavailable else P.GREY),
                Text(deployment.strategy, style=P.LILAC),
                Text(humanize_age(deployment.created), style=P.GREY),
                key=f"{deployment.namespace}/{deployment.name}",
            )
        self._restore(table, selected, offset)

    def _fill_events(self) -> None:
        if not self.snapshot or not self.snapshot.events:
            return
        table = self.query_one("#events", DataTable)
        offset = table.scroll_offset.y
        table.clear()
        for index, event in enumerate(self.snapshot.events):
            if self.namespace and event.namespace != self.namespace:
                continue
            if not self._matches(event.name, event.namespace, event.reason,
                                 event.message):
                continue
            warning = event.type != "Normal"
            table.add_row(
                Text(humanize_age(event.last), style=P.GREY),
                Text(event.type, style=P.MARS if warning else P.ANAKIWA),
                Text(event.reason[:22], style=P.SUNFLOWER if warning else P.TAN),
                Text(event.namespace[:16], style=P.PERIWINKLE),
                Text(f"{event.kind}/{event.name}"[:34], style=P.TAN),
                Text(str(event.count), style=P.LILAC),
                Text(event.message[:56], style=P.GREY),
                key=f"{index}",
            )
        table.scroll_to(y=offset, animate=False)

    @staticmethod
    def _selected_key(table: DataTable) -> str | None:
        try:
            row = table.coordinate_to_cell_key(table.cursor_coordinate)
            return row.row_key.value
        except Exception:
            return None

    @staticmethod
    def _restore(table: DataTable, key: str | None, offset: int) -> None:
        if key is not None:
            try:
                table.move_cursor(row=table.get_row_index(key), scroll=False)
            except Exception:
                pass
        table.scroll_to(y=offset, animate=False)

    def _update_table_bar(self) -> None:
        width = self.query_one("#table-bar", Static).size.width or 80
        _, column, _ = POD_SORTS[self.sort_index]
        titles = {"pods": "PODS", "nodes": "NODES", "events": "EVENTS",
                  "deployments": "DEPLOYMENTS"}
        counts = {"pods": len(self.visible_pods),
                  "nodes": len(self.visible_nodes),
                  "events": len(self.snapshot.events) if self.snapshot else 0,
                  "deployments": len(self.visible_deployments)}
        colour = {"pods": P.ORANGE, "nodes": P.LILAC, "events": P.TAN,
                  "deployments": P.PERIWINKLE}[self.view]

        value = Text()
        value.append(f"{counts[self.view]} ", style=P.TAN)
        value.append("SHOWN", style=P.GREY)
        if self.namespace:
            value.append("  NS ", style=P.GREY)
            value.append(self.namespace, style=P.ANAKIWA)
        if self.filter_text:
            value.append("  FILTER ", style=P.GREY)
            value.append(self.filter_text, style=P.SUNFLOWER)
        if self.view == "pods":
            value.append("  SORT ", style=P.GREY)
            value.append(f"{column}{'▼' if self.sort_reverse else '▲'}",
                         style=P.SUNFLOWER)
        label = titles[self.view] + (" — HOLD" if self.paused else "")
        bar = G.panel_bar(label, width, colour, G.lcars_code(72, counts[self.view]), value)
        self.query_one("#table-bar", Static).update(bar)

    def on_resize(self) -> None:
        width, height = self.size.width, self.size.height
        expanded_frame = width >= 140 and height >= 40
        self.query_one(LcarsHeader).styles.height = 5 if expanded_frame else 3
        self.query_one(LcarsFooter).styles.height = 3 if expanded_frame else 2
        self.query_one(LcarsSidebar).display = width >= 92
        meters = self.query_one("#meters")
        if height < 18:
            meters.display = False
        else:
            meters.display = not meters.has_class("hidden")
            meters.styles.height = 14 if height >= 50 else (
                12 if height >= 34 else (9 if height >= 26 else 7))
        self.call_after_refresh(self._update_table_bar)

    # -- status ----------------------------------------------------------
    def set_status(self, message: str, colour: str = P.ORANGE) -> None:
        footer = self.query_one(LcarsFooter)
        footer.status = message
        footer.status_colour = colour

    # -- view plumbing ---------------------------------------------------
    def _apply_view(self) -> None:
        for name in ("pods", "nodes", "events", "deployments"):
            self.query_one(f"#{name}", DataTable).set_class(name != self.view, "hidden")
        self.query_one(LcarsSidebar).view = self.view
        table = self.query_one(f"#{self.view}", DataTable)
        table.focus()
        self._update_table_bar()

    def action_view(self, name: str) -> None:
        if name == "help":
            self.action_help()
            return
        if name == self.view:
            return
        self.view = name
        self._apply_view()
        if name == "events":
            self.refresh_data()

    def action_cycle_view(self) -> None:
        order = ["pods", "nodes", "events", "deployments"]
        self.action_view(order[(order.index(self.view) + 1) % len(order)])

    def action_toggle_meters(self) -> None:
        meters = self.query_one("#meters")
        meters.toggle_class("hidden")
        self.on_resize()
        self.set_status("GRAPHS " + ("OFFLINE" if meters.has_class("hidden") else "ONLINE"))

    def action_cycle_namespace(self) -> None:
        if not self.snapshot:
            return
        options = [""] + sorted(self.snapshot.namespaces, key=str.casefold)
        try:
            index = options.index(self.namespace)
        except ValueError:
            index = 0
        self._set_namespace(options[(index + 1) % len(options)])

    def action_all_namespaces(self) -> None:
        self._set_namespace("")

    def _set_namespace(self, namespace: str) -> None:
        self.namespace = namespace
        self.query_one(LcarsSidebar).namespace = namespace
        self.set_status(f"NAMESPACE {namespace.upper() or 'ALL'}", P.ANAKIWA)
        if self.snapshot:
            self._fill_pods()
            self._fill_events()
            self._fill_deployments()
            self._update_table_bar()

    def on_lcars_sidebar_selected(self, message: LcarsSidebar.Selected) -> None:
        if message.kind == "view":
            self.action_view(message.value)
        elif message.kind == "namespace":
            self._set_namespace(message.value)
        elif message.kind == "pause":
            self.action_pause()

    def action_sort_step(self, delta: int) -> None:
        self.sort_index = (self.sort_index + delta) % len(POD_SORTS)
        if self.snapshot:
            self._fill_pods()
        self._update_table_bar()
        self.set_status(f"SORT {POD_SORTS[self.sort_index][1]}", P.SUNFLOWER)

    def action_reverse(self) -> None:
        self.sort_reverse = not self.sort_reverse
        if self.snapshot:
            self._fill_pods()
        self._update_table_bar()

    def on_data_table_header_selected(self, message: DataTable.HeaderSelected) -> None:
        if message.data_table.id != "pods":
            return
        key = message.column_key.value
        for index, (name, _, _) in enumerate(POD_SORTS):
            if name == key:
                if index == self.sort_index:
                    self.sort_reverse = not self.sort_reverse
                self.sort_index = index
                self._fill_pods()
                self._update_table_bar()
                return

    def action_pause(self) -> None:
        self.paused = not self.paused
        sidebar = self.query_one(LcarsSidebar)
        sidebar.paused = self.paused
        self._update_table_bar()
        self.set_status("SCAN HELD" if self.paused else "SCAN RESUMED",
                        P.MARS if self.paused else P.ORANGE)

    def action_interval(self, delta: int) -> None:
        steps = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0]
        current = min(range(len(steps)), key=lambda i: abs(steps[i] - self.interval))
        self.interval = steps[max(0, min(len(steps) - 1, current + delta))]
        self.query_one(LcarsSidebar).interval = self.interval
        self._schedule()
        self.set_status(f"SCAN INTERVAL {self.interval:g}S", P.LILAC)

    def action_refresh_now(self) -> None:
        self.refresh_data()
        self.set_status("MANUAL SCAN", P.ANAKIWA)

    # -- filter ----------------------------------------------------------
    def action_filter(self) -> None:
        field = self.query_one("#filter", Input)
        field.add_class("visible")
        field.focus()

    def action_clear(self) -> None:
        field = self.query_one("#filter", Input)
        if field.has_focus or self.filter_text:
            field.value = ""
            self.filter_text = ""
            field.remove_class("visible")
            if self.snapshot:
                self._fill_pods()
                self._fill_nodes()
                self._fill_events()
                self._fill_deployments()
            self._update_table_bar()
            self.query_one(f"#{self.view}", DataTable).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        self.filter_text = message.value.strip()
        if self.snapshot:
            self._fill_pods()
            self._fill_nodes()
            self._fill_events()
            self._fill_deployments()
        self._update_table_bar()

    def on_input_submitted(self) -> None:
        self.query_one(f"#{self.view}", DataTable).focus()

    # -- pod actions -----------------------------------------------------
    def _current_pod(self):
        if self.view != "pods":
            self.set_status("SELECT A POD FIRST — PRESS 2", P.SUNFLOWER)
            return None
        table = self.query_one("#pods", DataTable)
        index = table.cursor_row
        if index is None or index < 0 or index >= len(self.visible_pods):
            self.set_status("NO POD SELECTED", P.SUNFLOWER)
            return None
        return self.visible_pods[index]

    def action_logs(self) -> None:
        pod = self._current_pod()
        if pod:
            self.push_screen(LogScreen(self.source, pod))

    def action_detail(self) -> None:
        pod = self._current_pod()
        if pod:
            self.push_screen(DetailScreen(self.source, pod))

    def action_delete(self) -> None:
        pod = self._current_pod()
        if not pod:
            return

        def finish(confirmed: bool | None) -> None:
            if not confirmed:
                self.set_status("DELETE ABORTED", P.GREY)
                return
            self._delete_pod(pod.namespace, pod.name)

        self.push_screen(ConfirmScreen(pod), finish)

    @work(thread=True)
    def _delete_pod(self, namespace: str, name: str) -> None:
        try:
            message = self.source.delete_pod(namespace, name)
            self.call_from_thread(self.set_status, message, P.LILAC)
        except Exception as error:  # noqa: BLE001
            self.call_from_thread(self.set_status,
                                  f"DELETE FAILED · {error.__class__.__name__}", P.MARS)
        self.call_from_thread(self.refresh_data)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())
