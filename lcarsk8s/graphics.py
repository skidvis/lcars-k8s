from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pygame

from .cluster import Snapshot, humanize_age, humanize_bytes, humanize_cpu, stardate

W, H = 1920, 1080
BLACK = (0, 0, 0)
PANEL = (10, 8, 15)
ORANGE = (255, 153, 0)
PEACH = (255, 153, 102)
TAN = (255, 204, 153)
GOLD = (255, 204, 0)
LILAC = (204, 153, 204)
VIOLET = (153, 68, 255)
PERIWINKLE = (153, 153, 255)
ICE = (153, 204, 255)
MARS = (204, 68, 68)
TOMATO = (221, 102, 68)
WHITE = (245, 246, 250)
GREY = (92, 92, 122)
DIM = (45, 34, 54)

def shade_color(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(int(channel * amount) for channel in color)


SORTS = (
    ("cpu", "CPU", lambda pod: pod.cpu),
    ("mem", "MEM", lambda pod: pod.mem),
    ("restarts", "RST", lambda pod: pod.restarts),
    ("age", "AGE", lambda pod: -(pod.created.timestamp() if pod.created else 0)),
    ("status", "STATUS", lambda pod: pod.status),
    ("name", "POD", lambda pod: pod.name),
    ("namespace", "NS", lambda pod: (pod.namespace, pod.name)),
    ("node", "NODE", lambda pod: (pod.node, pod.name)),
)


class LcarsGraphics:
    def __init__(self, source, interval: float = 2.0, namespace: str = "",
                 view: str = "pods", windowed: bool = False,
                 resolution: tuple[int, int] | None = None,
                 sidebar: str = "left", show_graphs: bool = True) -> None:
        pygame.display.init()
        pygame.font.init()
        flags = pygame.RESIZABLE if windowed else pygame.FULLSCREEN
        if resolution is None:
            resolution = (1600, 900) if windowed else (0, 0)
        print(f"lcars-k8s: creating SDL surface size={resolution} "
              f"fullscreen={not windowed}", flush=True)
        self.screen = pygame.display.set_mode(resolution, flags)
        pygame.display.set_caption("LCARS K8S OPERATIONS")
        pygame.mouse.set_visible(bool(windowed and os.environ.get("DISPLAY")))
        self.canvas = pygame.Surface((W, H)).convert()
        print(f"lcars-k8s: SDL {pygame.get_sdl_version()} "
              f"driver={pygame.display.get_driver()} screen={self.screen.get_size()}",
              flush=True)
        self.source = source
        self.scaled = False
        self.interval = interval
        self.namespace = namespace
        self.view = view
        self.sidebar_side = sidebar
        self.snapshot: Snapshot | None = None
        self.history_cpu: list[float] = []
        self.history_mem: list[float] = []
        self.paused = False
        self.show_graphs = show_graphs
        self.filter_text = ""
        self.filtering = False
        self.sort_index = 5
        self.sort_reverse = False
        self.selected = 0
        self.scroll = 0
        self.status = "INITIALIZING SENSOR ARRAY"
        self.status_color = ORANGE
        self.modal = ""
        self.modal_text: list[str] = []
        self.modal_title = ""
        self.running = True
        self.last_poll = 0.0
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="lcars")
        self.poll_future: Future | None = None
        self.action_future: Future | None = None
        self.action_kind = ""
        self.fonts = self._fonts()
        self.clock = pygame.time.Clock()
        self.motion_started = time.monotonic()
        self.motion_time = 0.0
        self.presented = False
        self._start_poll()

    def _fonts(self) -> dict[str, pygame.font.Font]:
        bundled = Path(__file__).resolve().parent / "assets" / "Antonio.ttf"
        source = str(bundled) if bundled.exists() else pygame.font.match_font("dejavusans")
        return {
            "hero": pygame.font.Font(source, 46),
            "title": pygame.font.Font(source, 32),
            "label": pygame.font.Font(source, 25),
            "body": pygame.font.Font(source, 22),
            "small": pygame.font.Font(source, 18),
            "tiny": pygame.font.Font(source, 15),
        }

    def run(self) -> int:
        try:
            while self.running:
                self._events()
                self._collect()
                if not self.paused and time.monotonic() - self.last_poll >= self.interval:
                    self._start_poll()
                self.draw()
                self._present()
                self.clock.tick(30)
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)
            pygame.quit()
        return 0

    def _start_poll(self) -> None:
        if self.poll_future is None:
            self.poll_future = self.executor.submit(
                self.source.snapshot, self.view == "events")
            self.last_poll = time.monotonic()

    def _collect(self) -> None:
        if self.poll_future is not None and self.poll_future.done():
            future, self.poll_future = self.poll_future, None
            try:
                self.snapshot = future.result()
                self.history_cpu = (self.history_cpu + [self.snapshot.cpu_fraction])[-240:]
                self.history_mem = (self.history_mem + [self.snapshot.mem_fraction])[-240:]
                self.status = "SENSORS ONLINE"
                self.status_color = ICE
                self.selected = min(self.selected, max(0, len(self._rows()) - 1))
            except Exception as error:
                self.status = f"APISERVER {error.__class__.__name__}"
                self.status_color = MARS
        if self.action_future is not None and self.action_future.done():
            future, self.action_future = self.action_future, None
            try:
                result = future.result()
                if self.action_kind == "detail":
                    self._show_manifest(result)
                elif self.action_kind == "logs":
                    self.modal_text = str(result).splitlines()[-300:]
                    self.modal = "text"
                else:
                    self.modal = ""
                    self.status = str(result)
                    self.status_color = LILAC
                    self._start_poll()
            except Exception as error:
                self.modal = ""
                self.status = f"ACTION FAILED {error.__class__.__name__}"
                self.status_color = MARS
            self.action_kind = ""

    def _events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE and not self.scaled:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                self._key(event)

    def _key(self, event: pygame.event.Event) -> None:
        key = event.key
        if self.filtering:
            if key == pygame.K_ESCAPE:
                self.filtering = False
                self.filter_text = ""
            elif key == pygame.K_RETURN:
                self.filtering = False
            elif key == pygame.K_BACKSPACE:
                self.filter_text = self.filter_text[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.filter_text += event.unicode
            self.selected = 0
            self.scroll = 0
            return
        if self.modal == "confirm":
            if key in (pygame.K_y, pygame.K_RETURN):
                self._confirm_delete()
            elif key in (pygame.K_n, pygame.K_ESCAPE, pygame.K_q):
                self.modal = ""
            return
        if self.modal:
            if key in (pygame.K_ESCAPE, pygame.K_q):
                self.modal = ""
            elif key in (pygame.K_UP, pygame.K_k):
                self.scroll = max(0, self.scroll - 1)
            elif key in (pygame.K_DOWN, pygame.K_j):
                self.scroll += 1
            return
        if key == pygame.K_q:
            self.running = False
        elif key == pygame.K_1:
            self.show_graphs = not self.show_graphs
        elif key in (pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
            self.view = {pygame.K_2: "pods", pygame.K_3: "nodes",
                         pygame.K_4: "events", pygame.K_5: "deployments"}[key]
            self.selected = 0
            self.scroll = 0
            self._start_poll()
        elif key == pygame.K_TAB:
            order = ("pods", "nodes", "events", "deployments")
            self.view = order[(order.index(self.view) + 1) % len(order)]
            self.selected = 0
            self.scroll = 0
            self._start_poll()
        elif key == pygame.K_n:
            self._cycle_namespace()
        elif key == pygame.K_a:
            self.namespace = ""
            self.selected = 0
        elif key == pygame.K_SLASH and event.unicode == "?":
            self._help()
        elif key in (pygame.K_SLASH, pygame.K_f):
            self.filtering = True
        elif key in (pygame.K_COMMA, pygame.K_LESS):
            self.sort_index = (self.sort_index - 1) % len(SORTS)
        elif key in (pygame.K_PERIOD, pygame.K_GREATER):
            self.sort_index = (self.sort_index + 1) % len(SORTS)
        elif key == pygame.K_r and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            self._start_poll()
            self.status = "MANUAL SCAN"
            self.status_color = ICE
        elif key == pygame.K_r:
            self.sort_reverse = not self.sort_reverse
        elif key == pygame.K_SPACE:
            self.paused = not self.paused
            self.status = "SCAN HELD" if self.paused else "SCAN RESUMED"
            self.status_color = LILAC if self.paused else ICE
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.interval = min(30.0, self.interval + 1.0)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.interval = max(0.5, self.interval - 1.0)
        elif key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif key == pygame.K_DOWN:
            self.selected = min(max(0, len(self._rows()) - 1), self.selected + 1)
        elif key == pygame.K_PAGEUP:
            self.selected = max(0, self.selected - 15)
        elif key == pygame.K_PAGEDOWN:
            self.selected = min(max(0, len(self._rows()) - 1), self.selected + 15)
        elif key == pygame.K_HOME:
            self.selected = 0
        elif key == pygame.K_END:
            self.selected = max(0, len(self._rows()) - 1)
        elif key == pygame.K_d:
            self._detail()
        elif key == pygame.K_l:
            self._logs()
        elif key in (pygame.K_x, pygame.K_DELETE):
            self._delete()
        elif key == pygame.K_F5:
            self._start_poll()

    def _help(self) -> None:
        self.modal_title = "OPERATIONS MANUAL"
        self.modal_text = [
            "1                 SHOW OR HIDE CLUSTER GRAPHS",
            "2 / 3 / 4 / 5     PODS / NODES / EVENTS / DEPLOYMENTS",
            "TAB               CYCLE VIEWS",
            "N / A             NEXT NAMESPACE / ALL NAMESPACES",
            "/ OR F            FILTER CURRENT VIEW",
            "< / >             CHANGE POD SORT COLUMN",
            "R                 REVERSE SORT ORDER",
            "UP / DOWN         MOVE SELECTION",
            "L                 OPEN CONTAINER LOG",
            "D                 OPEN POD DETAIL AND MANIFEST",
            "X OR DELETE       DELETE POD WITH CONFIRMATION",
            "SPACE             HOLD OR RESUME SCANNING",
            "+ / -             CHANGE SCAN INTERVAL",
            "CTRL+R OR F5      SCAN NOW",
            "Q                 QUIT",
        ]
        self.scroll = 0
        self.modal = "text"

    def _cycle_namespace(self) -> None:
        options = [""] + (sorted(self.snapshot.namespaces, key=str.casefold)
                           if self.snapshot else [])
        try:
            index = options.index(self.namespace)
        except ValueError:
            index = 0
        self.namespace = options[(index + 1) % len(options)]
        self.selected = 0
        self.scroll = 0

    def _current_pod(self):
        rows = self._pod_rows()
        return rows[self.selected] if self.view == "pods" and rows else None

    def _detail(self) -> None:
        pod = self._current_pod()
        if pod is None or self.action_future is not None:
            self.status = "SELECT A POD FIRST"
            self.status_color = GOLD
            return
        self.modal_title = f"POD DETAIL  {pod.namespace}/{pod.name}"
        self.modal_text = ["READING MANIFEST"]
        self.scroll = 0
        self.modal = "text"
        self.action_kind = "detail"
        self.action_future = self.executor.submit(
            self.source.describe_pod, pod.namespace, pod.name)

    def _show_manifest(self, manifest: dict) -> None:
        pod = self._current_pod()
        prefix = []
        if pod is not None:
            prefix = [
                f"NAMESPACE     {pod.namespace}",
                f"NAME          {pod.name}",
                f"STATUS        {pod.status}",
                f"READY         {pod.ready}",
                f"RESTARTS      {pod.restarts}",
                f"NODE          {pod.node or 'UNSCHEDULED'}",
                f"OWNER         {pod.owner or 'NONE'}",
                "",
                "MANIFEST",
                "",
            ]
        self.modal_text = prefix + json.dumps(manifest, indent=2, default=str).splitlines()
        self.modal = "text"

    def _logs(self) -> None:
        pod = self._current_pod()
        if pod is None or self.action_future is not None:
            self.status = "SELECT A POD FIRST"
            self.status_color = GOLD
            return
        self.modal_title = f"CONTAINER LOG  {pod.namespace}/{pod.name}"
        self.modal_text = ["OPENING LOG CHANNEL"]
        self.scroll = 0
        self.modal = "text"
        self.action_kind = "logs"
        container = pod.containers[0] if pod.containers else None
        self.action_future = self.executor.submit(
            self.source.pod_logs, pod.namespace, pod.name, container, 500, False)

    def _delete(self) -> None:
        pod = self._current_pod()
        if pod is None:
            self.status = "SELECT A POD FIRST"
            self.status_color = GOLD
            return
        self.modal_title = "CONFIRM POD DELETE"
        self.modal_text = [f"{pod.namespace}/{pod.name}",
                           pod.owner or "UNOWNED POD WILL NOT RETURN",
                           "PRESS Y TO DELETE OR N TO CANCEL"]
        self.scroll = 0
        self.modal = "confirm"

    def _confirm_delete(self) -> None:
        pod = self._current_pod()
        if pod is None or self.action_future is not None:
            self.modal = ""
            return
        self.modal_text = ["DELETE COMMAND TRANSMITTED"]
        self.action_kind = "delete"
        self.action_future = self.executor.submit(
            self.source.delete_pod, pod.namespace, pod.name)

    def _pod_rows(self):
        if self.snapshot is None:
            return []
        needle = self.filter_text.lower()
        pods = [pod for pod in self.snapshot.pods
                if (not self.namespace or pod.namespace == self.namespace)
                and (not needle or any(needle in value.lower() for value in
                    (pod.namespace, pod.name, pod.node, pod.status)))]
        pods.sort(key=SORTS[self.sort_index][2], reverse=self.sort_reverse)
        return pods

    def _rows(self):
        if self.snapshot is None:
            return []
        if self.view == "pods":
            return self._pod_rows()
        needle = self.filter_text.lower()
        if self.view == "nodes":
            nodes = [node for node in self.snapshot.nodes if not needle or needle in
                     f"{node.name} {node.roles} {node.condition}".lower()]
            return sorted(nodes, key=lambda node: node.name.casefold())
        if self.view == "deployments":
            deployments = [deployment for deployment in self.snapshot.deployments
                           if (not self.namespace or
                               deployment.namespace == self.namespace)
                           and (not needle or needle in
                                f"{deployment.namespace} {deployment.name} "
                                f"{deployment.strategy}".lower())]
            return sorted(deployments,
                          key=lambda deployment: (deployment.name.casefold(),
                                                  deployment.namespace.casefold()))
        return [event for event in self.snapshot.events
                if (not self.namespace or event.namespace == self.namespace)
                and (not needle or needle in
                    f"{event.namespace} {event.name} {event.reason} {event.message}".lower())]

    def draw(self) -> None:
        self.motion_time = time.monotonic() - self.motion_started
        self.canvas.fill(BLACK)
        self._frame()
        self._data_sequencer()
        self._stats(139)
        if self.show_graphs:
            self._telemetry()
            table_y = 438
        else:
            table_y = 205
        self._table(table_y)
        self._footer()
        if self.filtering:
            self._filter_overlay()
        if self.modal:
            self._modal()

    def _main_x(self, x: int) -> int:
        return x if self.sidebar_side == "left" else x - 316

    def _frame(self) -> None:
        right = self.sidebar_side == "right"
        pygame.draw.rect(self.canvas, ORANGE, (24, 24, 1872, 48), border_radius=24)
        if right:
            pygame.draw.rect(self.canvas, PEACH, (1636, 24, 260, 130))
            pygame.draw.rect(self.canvas, ORANGE, (1856, 24, 40, 48))
            pygame.draw.circle(self.canvas, PEACH, (1636, 72), 48)
            pygame.draw.circle(self.canvas, BLACK, (1588, 120), 48)
            self._text("47-1701", 1865, 92, BLACK, "label", "right")
        else:
            pygame.draw.rect(self.canvas, PEACH, (24, 24, 260, 130))
            pygame.draw.rect(self.canvas, ORANGE, (24, 24, 40, 48))
            pygame.draw.circle(self.canvas, PEACH, (284, 72), 48)
            pygame.draw.circle(self.canvas, BLACK, (332, 120), 48)
            self._text("47-1701", 55, 92, BLACK, "label")
        main_start = self._main_x(365)
        main_end = self._main_x(1870)
        self._text("KUBERNETES OPERATIONS", main_start, 32, BLACK, "title")
        context = self.snapshot.context if self.snapshot else getattr(self.source, "context", self.source.name)
        version = self.snapshot.server_version if self.snapshot else "SCANNING"
        self._text(context.upper(), main_start, 92, TAN, "label")
        self._text(version.upper(), main_end, 92, ICE, "label", "right")
        self._text(f"STARDATE {stardate()}", main_end, 127, LILAC, "small", "right")
        self._scanner_rail(main_start, 76, 1531, 10, ORANGE, 0.0)
        nav = (("02", "PODS", ORANGE), ("03", "NODES", LILAC),
               ("04", "EVENTS", TAN), ("05", "DEPLOYMENTS", PERIWINKLE))
        y = 190
        for key, label, color in nav:
            active = self.view == label.lower()
            width = 280 if active else 238
            x = W - 24 - width if right else 24
            pygame.draw.rect(self.canvas, color, (x, y, width, 62), border_radius=30)
            edge_x = x + width - 45 if right else x
            pygame.draw.rect(self.canvas, color, (edge_x, y, 45, 62))
            text_x = x + width - 26 if right else x + 26
            align = "right" if right else "left"
            self._text(f"{key}  {label}", text_x, y + 16, BLACK, "label", align)
            y += 82
        x = W - 24 - 238 if right else 24
        pygame.draw.rect(self.canvas, ORANGE, (x, y + 8, 238, 44), border_radius=22)
        edge_x = x + 200 if right else x
        pygame.draw.rect(self.canvas, ORANGE, (edge_x, y + 8, 38, 44))
        text_x = x + 212 if right else x + 26
        align = "right" if right else "left"
        self._text("NAMESPACE", text_x, y + 17, BLACK, "small", align)
        y += 70
        namespace_names = (sorted(self.snapshot.namespaces, key=str.casefold)
                           if self.snapshot else [])
        namespaces = [("", "ALL")] + [
            (name, name.upper()) for name in namespace_names]
        for value, label in namespaces[:8]:
            selected = self.namespace == value
            if selected:
                pygame.draw.rect(self.canvas, ICE, (x, y, 238, 34), border_radius=17)
                edge_x = x + 213 if right else x
                pygame.draw.rect(self.canvas, ICE, (edge_x, y, 25, 34))
            text_x = x + 17 if right else x + 221
            align = "left" if right else "right"
            self._text(label, text_x, y + 5, BLACK if selected else TAN,
                       "small", align)
            y += 38

    def _telemetry(self) -> None:
        self._graph_panel(self._main_x(340), 205, 735, 205, "CLUSTER CPU", "31-882",
                          self.history_cpu, self.snapshot.cpu_fraction if self.snapshot else 0,
                          ORANGE, "cpu")
        self._graph_panel(self._main_x(1110), 205, 786, 205, "CLUSTER MEMORY", "44-119",
                          self.history_mem, self.snapshot.mem_fraction if self.snapshot else 0,
                          LILAC, "mem")

    def _graph_panel(self, x: int, y: int, width: int, height: int, label: str,
                     code: str, values: list[float], fraction: float,
                     color: tuple[int, int, int], kind: str) -> None:
        pygame.draw.rect(self.canvas, color, (x, y, width, 38), border_radius=19)
        self._text(label, x + 22, y + 7, BLACK, "small")
        self._text(code, x + width - 18, y + 7, BLACK, "small", "right")
        plot = pygame.Rect(x, y + 48, width, height - 48)
        pygame.draw.rect(self.canvas, PANEL, plot)
        scan_x = plot.x + int((self.motion_time * 49.58) % plot.width)
        pygame.draw.line(self.canvas, shade_color(color, 0.35),
                         (scan_x, plot.y), (scan_x, plot.bottom), 2)
        for step in range(1, 4):
            gy = plot.bottom - step * plot.height // 4
            pygame.draw.line(self.canvas, DIM, (plot.x, gy), (plot.right, gy), 1)
        data = values[-120:]
        if data:
            dx = plot.width / max(1, len(data) - 1)
            points = [(plot.x + index * dx, plot.bottom - value * plot.height)
                      for index, value in enumerate(data)]
            fill = [(plot.x, plot.bottom)] + points + [(plot.right, plot.bottom)]
            shade = tuple(max(0, channel // 3) for channel in color)
            pygame.draw.polygon(self.canvas, shade, fill)
            if len(points) > 1:
                pygame.draw.lines(self.canvas, color, False, points, 4)
            else:
                pygame.draw.circle(self.canvas, color, points[0], 4)
            pulse = 6 + int((math.sin(self.motion_time * 4.355) + 1) * 3)
            pygame.draw.circle(self.canvas, shade_color(color, 0.65),
                               points[-1], pulse + 5, 3)
            pygame.draw.circle(self.canvas, WHITE, points[-1], 5)
        self._text(f"{fraction * 100:05.1f}%", x + 24, y + 65,
                   self._load_color(fraction), "hero")
        if self.snapshot:
            used = self.snapshot.cpu_used if kind == "cpu" else self.snapshot.mem_used
            capacity = self.snapshot.cpu_capacity if kind == "cpu" else self.snapshot.mem_capacity
            value = (f"{humanize_cpu(used)} / {humanize_cpu(capacity)}" if kind == "cpu"
                     else f"{humanize_bytes(used)} / {humanize_bytes(capacity)}")
            self._text(value, x + 26, y + 116, TAN, "body")
            nodes = sorted(self.snapshot.nodes,
                           key=lambda node: getattr(node, f"{kind}_fraction"), reverse=True)[:5]
            meter_x = x + width - 238
            for index, node in enumerate(nodes):
                ratio = getattr(node, f"{kind}_fraction")
                my = y + 58 + index * 27
                self._text(node.short_name[-10:], meter_x - 10, my, TAN, "tiny", "right")
                pygame.draw.rect(self.canvas, DIM, (meter_x, my + 2, 120, 16), border_radius=8)
                pygame.draw.rect(self.canvas, self._load_color(ratio),
                                 (meter_x, my + 2, max(4, int(120 * ratio)), 16), border_radius=8)
                self._text(f"{ratio * 100:3.0f}%", meter_x + 136, my, self._load_color(ratio), "tiny")

    def _stats(self, y: int) -> None:
        if self.snapshot is None:
            self._text("AWAITING TELEMETRY", self._main_x(340), y + 10, GREY, "label")
            return
        counts = self.snapshot.counts()
        ready = sum(1 for node in self.snapshot.nodes if node.ready)
        restarts = sum(pod.restarts for pod in self.snapshot.pods)
        cells = (("NODES", f"{ready}/{len(self.snapshot.nodes)}", ORANGE),
                 ("PODS", str(len(self.snapshot.pods)), TAN),
                 ("RUN", str(counts["running"]), ICE),
                 ("PEND", str(counts["pending"]), GOLD),
                 ("FAIL", str(counts["failed"]), MARS if counts["failed"] else GREY),
                 ("RESTARTS", str(restarts), LILAC))
        x = self._main_x(365)
        for label, value, color in cells:
            label_surface = self.fonts["small"].render(label, True, BLACK)
            box_width = label_surface.get_width() + 28
            pygame.draw.rect(self.canvas, color, (x, y + 8, box_width, 34), border_radius=17)
            self.canvas.blit(label_surface, (x + 14, y + 14))
            self._text(value, x + box_width + 10, y + 12, color, "small")
            x += box_width + self.fonts["small"].size(value)[0] + 38

    def _table(self, y: int) -> None:
        x, width = self._main_x(340), 1556
        rows = self._rows()
        title = self.view.upper()
        color = {"pods": ORANGE, "nodes": LILAC, "events": TAN,
                 "deployments": PERIWINKLE}[self.view]
        pygame.draw.rect(self.canvas, color, (x, y, width, 42), border_radius=21)
        self._text(title, x + 22, y + 8, BLACK, "label")
        right = f"{len(rows)} SHOWN"
        if self.namespace:
            right += f"   NS {self.namespace}"
        if self.view == "pods":
            right += f"   SORT {SORTS[self.sort_index][1]}{'▼' if self.sort_reverse else '▲'}"
        self._text(right, x + width - 22, y + 10, BLACK, "small", "right")
        header_y = y + 50
        pygame.draw.rect(self.canvas, color, (x, header_y, width, 34))
        if self.view == "pods":
            columns = (("NS", 18), ("POD", 190), ("NODE", 650), ("STATUS", 890),
                       ("READY", 1080), ("RST", 1180), ("CPU", 1260),
                       ("CPU%", 1350), ("MEM", 1430), ("AGE", 1510))
        elif self.view == "nodes":
            columns = (("NODE", 18), ("STATUS", 360), ("ROLES", 520),
                       ("CPU", 760), ("MEMORY", 1030), ("PODS", 1260),
                       ("VERSION", 1370), ("AGE", 1490))
        elif self.view == "deployments":
            columns = (("NS", 18), ("DEPLOYMENT", 190), ("READY", 730),
                       ("UP-TO-DATE", 860), ("AVAILABLE", 1050),
                       ("UNAVAILABLE", 1220), ("STRATEGY", 1400),
                       ("AGE", 1510))
        else:
            columns = (("AGE", 18), ("TYPE", 120), ("REASON", 240),
                       ("NS", 500), ("OBJECT", 700), ("N", 1040),
                       ("MESSAGE", 1110))
        for label, offset in columns:
            self._text(label, x + offset, header_y + 6, BLACK, "small")
        row_height = 31
        available = max(1, (990 - (header_y + 42)) // row_height)
        self.scroll = min(self.scroll, self.selected)
        if self.selected >= self.scroll + available:
            self.scroll = self.selected - available + 1
        visible = rows[self.scroll:self.scroll + available]
        for index, item in enumerate(visible):
            row_index = self.scroll + index
            ry = header_y + 40 + index * row_height
            if row_index == self.selected:
                pygame.draw.rect(self.canvas, LILAC, (x, ry - 1, width, row_height))
            selected = row_index == self.selected
            self._table_row(item, x, ry, selected)

    def _table_row(self, item, x: int, y: int, selected: bool) -> None:
        fg = BLACK if selected else TAN
        if self.view == "pods":
            capacity = {node.name: node for node in self.snapshot.nodes} if self.snapshot else {}
            node = capacity.get(item.node)
            cpu_ratio = item.cpu / item.cpu_limit if item.cpu_limit else (
                item.cpu / node.cpu_capacity if node and node.cpu_capacity else 0)
            values = ((item.namespace, 18, PERIWINKLE), (item.name, 190, fg),
                      (item.node.split(".")[0] or "-", 650, GREY),
                      (item.status, 890, ICE if item.healthy else MARS),
                      (item.ready, 1080, ICE), (str(item.restarts or "·"), 1180, MARS if item.restarts else GREY),
                      (humanize_cpu(item.cpu) if item.cpu else "·", 1260, PERIWINKLE),
                      (f"{cpu_ratio * 100:.0f}%", 1350, self._load_color(cpu_ratio)),
                      (humanize_bytes(item.mem) if item.mem else "·", 1430, VIOLET),
                      (humanize_age(item.created), 1510, GREY))
        elif self.view == "nodes":
            values = ((item.name, 18, fg), (item.condition, 360, ICE if item.ready else MARS),
                      (item.roles, 520, LILAC), (f"{item.cpu_fraction * 100:.0f}%", 760, self._load_color(item.cpu_fraction)),
                      (f"{item.mem_fraction * 100:.0f}%", 1030, self._load_color(item.mem_fraction)),
                      (f"{item.pod_count}/{item.pod_capacity}", 1260, TAN),
                      (item.version, 1370, GREY), (humanize_age(item.created), 1490, GREY))
        elif self.view == "deployments":
            health = ICE if item.healthy else MARS
            values = ((item.namespace, 18, PERIWINKLE), (item.name, 190, fg),
                      (f"{item.ready}/{item.replicas}", 730, health),
                      (str(item.updated), 860, ICE),
                      (str(item.available), 1050, ICE),
                      (str(item.unavailable), 1220, MARS if item.unavailable else GREY),
                      (item.strategy, 1400, LILAC),
                      (humanize_age(item.created), 1510, GREY))
        else:
            warning = item.type != "Normal"
            values = ((humanize_age(item.last), 18, GREY), (item.type, 120, MARS if warning else ICE),
                      (item.reason, 240, GOLD if warning else TAN), (item.namespace, 500, PERIWINKLE),
                      (f"{item.kind}/{item.name}", 700, TAN), (str(item.count), 1040, LILAC),
                      (item.message, 1110, GREY))
        for index, (value, offset, color) in enumerate(values):
            next_offset = values[index + 1][1] if index + 1 < len(values) else 1556
            width = max(30, next_offset - offset - 18)
            self._text_clip(str(value), x + offset, y + 3,
                            color if not selected else BLACK, "small", width)

    def _data_sequencer(self) -> None:
        phase = int(self.motion_time * 3.35)
        colors = (GOLD, ORANGE, PEACH, LILAC, PERIWINKLE, ICE)
        for index in range(16):
            y = 184 + index * 48
            value = (phase * 17 + index * 31) % 100
            color = colors[(phase // 2 + index) % len(colors)]
            if self.sidebar_side == "right":
                self._text(f"{value:02}", 1588, y, color, "label")
            else:
                self._text(f"{value:02}", 332, y, color, "label", "right")

    def _footer(self) -> None:
        right = self.sidebar_side == "right"
        self._scanner_rail(self._main_x(340), 998, 1556, 9, LILAC, 0.55)
        footer_x = 1636 if right else 24
        pygame.draw.rect(self.canvas, LILAC, (footer_x, 1012, 260, 44))
        pygame.draw.rect(self.canvas, self.status_color, (24, 1036, 1872, 28), border_radius=14)
        edge_x = 1856 if right else 24
        pygame.draw.rect(self.canvas, self.status_color, (edge_x, 1036, 40, 28))
        legend = "2-5 VIEW   N NAMESPACE   / FILTER   <> SORT   R REVERSE   L LOGS   D DETAIL   X DELETE   SPACE HOLD   ? HELP   Q QUIT"
        self._text(legend, self._main_x(340), 1018, TAN, "tiny")
        light = int(self.motion_time * 2.68) % 3
        for index in range(3):
            color = self.status_color if index == light else shade_color(self.status_color, 0.28)
            light_x = 1610 - index * 13 if right else 310 + index * 13
            pygame.draw.circle(self.canvas, color, (light_x, 1050), 4)
        self._text(self.status, self._main_x(1870), 1041, BLACK, "small", "right")

    def _scanner_rail(self, x: int, y: int, width: int, height: int,
                      color: tuple[int, int, int], offset: float) -> None:
        pygame.draw.rect(self.canvas, shade_color(color, 0.22), (x, y, width, height))
        segment = 190
        travel = width + segment
        head = x + int(((self.motion_time * 0.2278 + offset) % 1.0) * travel) - segment
        start = max(x, head)
        end = min(x + width, head + segment)
        if end > start:
            pygame.draw.rect(self.canvas, color, (start, y, end - start, height))
        gap = 11
        pygame.draw.rect(self.canvas, BLACK, (x + width // 3, y, gap, height))
        pygame.draw.rect(self.canvas, BLACK, (x + width * 2 // 3, y, gap, height))

    def _filter_overlay(self) -> None:
        pygame.draw.rect(self.canvas, BLACK, (520, 948, 1120, 58), border_radius=29)
        pygame.draw.rect(self.canvas, GOLD, (520, 948, 1120, 58), width=3, border_radius=29)
        self._text(f"FILTER  {self.filter_text}_", 550, 962, GOLD, "label")

    def _modal(self) -> None:
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 205))
        self.canvas.blit(shade, (0, 0))
        rect = pygame.Rect(245, 125, 1430, 820)
        color = MARS if self.modal == "confirm" else ICE
        pygame.draw.rect(self.canvas, PANEL, rect, border_radius=34)
        pygame.draw.rect(self.canvas, color, rect, width=6, border_radius=34)
        pygame.draw.rect(self.canvas, color, (rect.x, rect.y, 190, rect.height),
                         border_top_left_radius=34, border_bottom_left_radius=34)
        pygame.draw.rect(self.canvas, color, (rect.x + 220, rect.y, rect.width - 220, 54),
                         border_top_right_radius=27, border_bottom_right_radius=27)
        self._text(self.modal_title, rect.x + 250, rect.y + 12, BLACK, "label")
        body_x, body_y = rect.x + 230, rect.y + 82
        visible = self.modal_text[self.scroll:self.scroll + 29]
        for index, line in enumerate(visible):
            self._text_clip(line, body_x, body_y + index * 24,
                            MARS if self.modal == "confirm" and index == 0 else TAN,
                            "small", rect.width - 270)
        hint = "Y DELETE   N CANCEL" if self.modal == "confirm" else "ESC CLOSE   ↑↓ SCROLL"
        self._text(hint, rect.right - 30, rect.bottom - 42, color, "small", "right")

    def _load_color(self, value: float) -> tuple[int, int, int]:
        if value >= 0.85:
            return MARS
        if value >= 0.65:
            return ORANGE
        if value >= 0.4:
            return LILAC
        return PERIWINKLE

    def _text(self, value: str, x: int, y: int, color: tuple[int, int, int],
              font: str, align: str = "left") -> None:
        surface = self.fonts[font].render(value, True, color)
        if align == "right":
            x -= surface.get_width()
        self.canvas.blit(surface, (x, y))

    def _text_clip(self, value: str, x: int, y: int, color: tuple[int, int, int],
                   font: str, width: int) -> None:
        face = self.fonts[font]
        text = value
        while text and face.size(text)[0] > width:
            text = text[:-1]
        if text != value and len(text) > 1:
            text = text[:-1] + "…"
        self._text(text, x, y, color, font)

    def _present(self) -> None:
        size = self.screen.get_size()
        if size == (W, H):
            self.screen.blit(self.canvas, (0, 0))
        else:
            scaled = pygame.transform.smoothscale(self.canvas, size)
            self.screen.blit(scaled, (0, 0))
        pygame.display.flip()
        if not self.presented:
            pygame.image.save(self.canvas, "/tmp/lcars-k8s-live-frame.png")
            self.presented = True
            print("lcars-k8s: first frame presented and saved to "
                  "/tmp/lcars-k8s-live-frame.png", flush=True)
