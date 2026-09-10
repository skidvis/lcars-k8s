"""Cluster data layer.

Everything that talks to the API server lives here and is called from worker
threads, so the UI never blocks on a slow apiserver. Two sources are
provided: :class:`KubeSource` for a real cluster and :class:`DemoSource`
which synthesises a plausible cluster for previewing the interface.
"""

from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

CPU_SUFFIX = {
    "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0,
    "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18,
    "Ki": 2 ** 10, "Mi": 2 ** 20, "Gi": 2 ** 30,
    "Ti": 2 ** 40, "Pi": 2 ** 50, "Ei": 2 ** 60,
}


def parse_quantity(value) -> float:
    """Parse a Kubernetes resource quantity into a plain float.

    CPU comes back in cores, memory and storage in bytes. Handles the binary
    (``Ki``/``Mi``), decimal (``k``/``M``) and small (``n``/``u``/``m``)
    suffixes as well as scientific notation.
    """
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    cut = len(text)
    while cut > 0 and text[cut - 1].isalpha():
        cut -= 1
    number, suffix = text[:cut], text[cut:]
    try:
        magnitude = float(number)
    except ValueError:
        return 0.0
    return magnitude * CPU_SUFFIX.get(suffix, 1.0)


def humanize_bytes(value: float) -> str:
    if value <= 0:
        return "0B"
    for unit, size in (("T", 2 ** 40), ("G", 2 ** 30), ("M", 2 ** 20), ("K", 2 ** 10)):
        if value >= size:
            scaled = value / size
            return f"{scaled:.1f}{unit}" if scaled < 100 else f"{scaled:.0f}{unit}"
    return f"{value:.0f}B"


def humanize_cpu(cores: float) -> str:
    if cores >= 10:
        return f"{cores:.0f}c"
    if cores >= 1:
        return f"{cores:.2f}c"
    return f"{cores * 1000:.0f}m"


def humanize_age(started: datetime | None) -> str:
    if started is None:
        return "-"
    seconds = int((datetime.now(timezone.utc) - started).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s" if minutes < 10 else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m" if hours < 10 else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h" if days < 10 else f"{days}d"


def stardate(now: datetime | None = None) -> str:
    """A stardate, because the interface demands one."""
    now = now or datetime.now(timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    fraction = (now - start).total_seconds() / (365.25 * 86400)
    return f"{(now.year - 1946) * 1000 + fraction * 1000:.1f}"


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------
@dataclass
class Node:
    name: str
    ready: bool = True
    schedulable: bool = True
    condition: str = "Ready"
    roles: str = ""
    version: str = ""
    created: datetime | None = None
    cpu_used: float = 0.0
    cpu_capacity: float = 0.0
    mem_used: float = 0.0
    mem_capacity: float = 0.0
    pod_count: int = 0
    pod_capacity: int = 0
    internal_ip: str = ""
    os_image: str = ""

    @property
    def cpu_fraction(self) -> float:
        return self.cpu_used / self.cpu_capacity if self.cpu_capacity else 0.0

    @property
    def mem_fraction(self) -> float:
        return self.mem_used / self.mem_capacity if self.mem_capacity else 0.0

    @property
    def pod_fraction(self) -> float:
        return self.pod_count / self.pod_capacity if self.pod_capacity else 0.0

    @property
    def short_name(self) -> str:
        return self.name.split(".")[0]


@dataclass
class Pod:
    namespace: str
    name: str
    node: str = ""
    status: str = "Unknown"
    ready: str = "0/0"
    ready_fraction: float = 0.0
    restarts: int = 0
    cpu: float = 0.0
    mem: float = 0.0
    cpu_request: float = 0.0
    mem_request: float = 0.0
    cpu_limit: float = 0.0
    mem_limit: float = 0.0
    created: datetime | None = None
    ip: str = ""
    qos: str = ""
    containers: tuple[str, ...] = ()
    owner: str = ""
    message: str = ""

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"

    @property
    def healthy(self) -> bool:
        return self.status in ("Running", "Succeeded", "Completed")


@dataclass
class Deployment:
    namespace: str
    name: str
    ready: int = 0
    replicas: int = 0
    updated: int = 0
    available: int = 0
    unavailable: int = 0
    strategy: str = "RollingUpdate"
    created: datetime | None = None

    @property
    def healthy(self) -> bool:
        return self.ready >= self.replicas and self.unavailable == 0


@dataclass
class Event:
    namespace: str
    name: str
    kind: str
    reason: str
    type: str
    message: str
    count: int
    last: datetime | None


@dataclass
class Snapshot:
    taken: float = field(default_factory=time.time)
    context: str = "-"
    server_version: str = "-"
    nodes: list[Node] = field(default_factory=list)
    pods: list[Pod] = field(default_factory=list)
    deployments: list[Deployment] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    metrics_available: bool = False
    errors: list[str] = field(default_factory=list)

    # -- cluster rollups -------------------------------------------------
    @property
    def cpu_used(self) -> float:
        return sum(n.cpu_used for n in self.nodes)

    @property
    def cpu_capacity(self) -> float:
        return sum(n.cpu_capacity for n in self.nodes)

    @property
    def mem_used(self) -> float:
        return sum(n.mem_used for n in self.nodes)

    @property
    def mem_capacity(self) -> float:
        return sum(n.mem_capacity for n in self.nodes)

    @property
    def cpu_fraction(self) -> float:
        return self.cpu_used / self.cpu_capacity if self.cpu_capacity else 0.0

    @property
    def mem_fraction(self) -> float:
        return self.mem_used / self.mem_capacity if self.mem_capacity else 0.0

    def counts(self) -> dict[str, int]:
        tally = {"running": 0, "pending": 0, "failed": 0, "succeeded": 0, "other": 0}
        for pod in self.pods:
            if pod.status == "Running":
                tally["running"] += 1
            elif pod.status in ("Succeeded", "Completed"):
                tally["succeeded"] += 1
            elif pod.status in ("Pending", "ContainerCreating", "PodInitializing"):
                tally["pending"] += 1
            elif pod.status in ("Failed", "Error", "CrashLoopBackOff",
                                "ImagePullBackOff", "ErrImagePull", "OOMKilled",
                                "Evicted"):
                tally["failed"] += 1
            else:
                tally["other"] += 1
        return tally


class ClusterError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Live cluster
# --------------------------------------------------------------------------
class KubeSource:
    """Reads a real cluster through the official Python client."""

    name = "kubernetes"

    def __init__(self, kubeconfig: str | None = None, context: str | None = None,
                 timeout: int = 10):
        from kubernetes import client, config
        from kubernetes.config.config_exception import ConfigException

        self._client = client
        self.timeout = timeout
        self.context = context or "-"
        try:
            config.load_kube_config(config_file=kubeconfig, context=context)
            try:
                _, active = config.list_kube_config_contexts(config_file=kubeconfig)
                self.context = context or (active or {}).get("name", "-")
            except Exception:
                pass
        except (ConfigException, FileNotFoundError, TypeError):
            try:
                config.load_incluster_config()
                self.context = "in-cluster"
            except ConfigException as exc:
                raise ClusterError(
                    "No usable kubeconfig and not running inside a pod. "
                    "Set KUBECONFIG or pass --kubeconfig."
                ) from exc

        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()
        self.custom = client.CustomObjectsApi()
        self.version_api = client.VersionApi()
        self._server_version = "-"
        self._metrics_warned = False

    # -- helpers ---------------------------------------------------------
    def _server(self) -> str:
        if self._server_version == "-":
            try:
                info = self.version_api.get_code(_request_timeout=self.timeout)
                self._server_version = info.git_version
            except Exception:
                self._server_version = "unknown"
        return self._server_version

    def _node_metrics(self, errors: list[str]) -> dict[str, tuple[float, float]]:
        try:
            payload = self.custom.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "nodes", _request_timeout=self.timeout)
        except Exception as exc:
            errors.append(f"node metrics unavailable ({_brief(exc)})")
            return {}
        result = {}
        for item in payload.get("items", []):
            usage = item.get("usage", {})
            result[item["metadata"]["name"]] = (
                parse_quantity(usage.get("cpu")), parse_quantity(usage.get("memory")))
        return result

    def _pod_metrics(self, errors: list[str]) -> dict[str, tuple[float, float]]:
        try:
            payload = self.custom.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "pods", _request_timeout=self.timeout)
        except Exception as exc:
            errors.append(f"pod metrics unavailable ({_brief(exc)})")
            return {}
        result = {}
        for item in payload.get("items", []):
            meta = item["metadata"]
            cpu = mem = 0.0
            for container in item.get("containers", []):
                usage = container.get("usage", {})
                cpu += parse_quantity(usage.get("cpu"))
                mem += parse_quantity(usage.get("memory"))
            result[f"{meta['namespace']}/{meta['name']}"] = (cpu, mem)
        return result

    # -- main fetch ------------------------------------------------------
    def snapshot(self, want_events: bool = False) -> Snapshot:
        errors: list[str] = []
        snap = Snapshot(context=self.context, server_version=self._server())

        try:
            node_list = self.core.list_node(_request_timeout=self.timeout).items
        except Exception as exc:
            raise ClusterError(f"cannot list nodes: {_brief(exc)}") from exc

        try:
            pod_list = self.core.list_pod_for_all_namespaces(
                _request_timeout=self.timeout).items
        except Exception as exc:
            errors.append(f"pod list failed ({_brief(exc)})")
            pod_list = []

        try:
            deployment_list = self.apps.list_deployment_for_all_namespaces(
                _request_timeout=self.timeout).items
        except Exception as exc:
            errors.append(f"deployment list failed ({_brief(exc)})")
            deployment_list = []

        node_usage = self._node_metrics(errors)
        pod_usage = self._pod_metrics(errors)
        snap.metrics_available = bool(node_usage or pod_usage)

        pods_per_node: dict[str, int] = {}
        for raw in pod_list:
            pod = _convert_pod(raw, pod_usage)
            snap.pods.append(pod)
            if pod.node:
                pods_per_node[pod.node] = pods_per_node.get(pod.node, 0) + 1

        # Without metrics-server, fall back to summed requests so the meters
        # still say something true, just about allocation instead of usage.
        requests_per_node: dict[str, tuple[float, float]] = {}
        if not snap.metrics_available:
            for pod in snap.pods:
                if not pod.node:
                    continue
                cpu, mem = requests_per_node.get(pod.node, (0.0, 0.0))
                requests_per_node[pod.node] = (cpu + pod.cpu_request, mem + pod.mem_request)

        for raw in node_list:
            node = _convert_node(raw)
            node.pod_count = pods_per_node.get(node.name, 0)
            if node.name in node_usage:
                node.cpu_used, node.mem_used = node_usage[node.name]
            elif node.name in requests_per_node:
                node.cpu_used, node.mem_used = requests_per_node[node.name]
            snap.nodes.append(node)

        snap.nodes.sort(key=lambda n: n.name)
        snap.deployments = sorted(
            (_convert_deployment(item) for item in deployment_list),
            key=lambda deployment: (deployment.name, deployment.namespace),
        )
        snap.namespaces = sorted(
            {pod.namespace for pod in snap.pods}
            | {deployment.namespace for deployment in snap.deployments}
        )

        if want_events:
            try:
                raw_events = self.core.list_event_for_all_namespaces(
                    limit=300, _request_timeout=self.timeout).items
                snap.events = sorted(
                    (_convert_event(e) for e in raw_events),
                    key=lambda e: e.last or datetime.fromtimestamp(0, timezone.utc),
                    reverse=True)
            except Exception as exc:
                errors.append(f"events unavailable ({_brief(exc)})")

        snap.errors = errors
        return snap

    # -- actions ---------------------------------------------------------
    def delete_pod(self, namespace: str, name: str, grace: int | None = None) -> str:
        body = self._client.V1DeleteOptions(grace_period_seconds=grace) if grace is not None else None
        self.core.delete_namespaced_pod(name=name, namespace=namespace, body=body,
                                        _request_timeout=self.timeout)
        return f"DELETE ISSUED · {namespace}/{name}"

    def pod_logs(self, namespace: str, name: str, container: str | None = None,
                 tail: int = 400, previous: bool = False) -> str:
        return self.core.read_namespaced_pod_log(
            name=name, namespace=namespace, container=container, tail_lines=tail,
            previous=previous, timestamps=False, _request_timeout=self.timeout)


    def describe_pod(self, namespace: str, name: str) -> dict:
        pod = self.core.read_namespaced_pod(name=name, namespace=namespace,
                                            _request_timeout=self.timeout)
        return self._client.ApiClient().sanitize_for_serialization(pod)


def _brief(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    first = text[0] if text else exc.__class__.__name__
    return first[:70]


def _convert_node(raw) -> Node:
    status = raw.status or None
    allocatable = (status.allocatable if status else {}) or {}
    labels = (raw.metadata.labels or {})
    roles = sorted(
        key.split("/", 1)[1] or "master"
        for key in labels
        if key.startswith("node-role.kubernetes.io/")
    )
    ready = False
    condition = "Unknown"
    for entry in (status.conditions if status else []) or []:
        if entry.type == "Ready":
            ready = entry.status == "True"
            condition = "Ready" if ready else (entry.reason or "NotReady")
    unschedulable = bool(raw.spec and raw.spec.unschedulable)
    if unschedulable:
        condition = "Cordoned"

    internal_ip = ""
    for address in (status.addresses if status else []) or []:
        if address.type == "InternalIP":
            internal_ip = address.address

    return Node(
        name=raw.metadata.name,
        ready=ready,
        schedulable=not unschedulable,
        condition=condition,
        roles=",".join(roles) if roles else "worker",
        version=(status.node_info.kubelet_version if status and status.node_info else ""),
        created=raw.metadata.creation_timestamp,
        cpu_capacity=parse_quantity(allocatable.get("cpu")),
        mem_capacity=parse_quantity(allocatable.get("memory")),
        pod_capacity=int(parse_quantity(allocatable.get("pods")) or 110),
        internal_ip=internal_ip,
        os_image=(status.node_info.os_image if status and status.node_info else ""),
    )


_WAITING_NOISE = {"PodInitializing", "ContainerCreating"}


def _convert_pod(raw, usage: dict[str, tuple[float, float]]) -> Pod:
    meta, spec, status = raw.metadata, raw.spec, raw.status
    key = f"{meta.namespace}/{meta.name}"

    state = (status.phase if status else "Unknown") or "Unknown"
    message = ""
    statuses = (status.container_statuses if status else None) or []
    init_statuses = (status.init_container_statuses if status else None) or []
    restarts = sum(cs.restart_count or 0 for cs in statuses + init_statuses)

    ready_count = sum(1 for cs in statuses if cs.ready)
    total = len(statuses) or len(spec.containers or [])

    for cs in init_statuses:
        waiting = cs.state.waiting if cs.state else None
        terminated = cs.state.terminated if cs.state else None
        if waiting and waiting.reason and waiting.reason not in _WAITING_NOISE:
            state, message = waiting.reason, waiting.message or ""
        elif terminated and terminated.exit_code not in (0, None):
            state = f"Init:{terminated.reason or 'Error'}"

    for cs in statuses:
        waiting = cs.state.waiting if cs.state else None
        terminated = cs.state.terminated if cs.state else None
        if waiting and waiting.reason:
            if waiting.reason not in _WAITING_NOISE or state == "Pending":
                state, message = waiting.reason, waiting.message or ""
        elif terminated and terminated.reason and terminated.reason != "Completed":
            state, message = terminated.reason, terminated.message or ""

    if status and status.reason:
        state = status.reason
    if meta.deletion_timestamp:
        state = "Terminating"

    cpu_request = mem_request = cpu_limit = mem_limit = 0.0
    for container in (spec.containers or []):
        resources = container.resources
        requests = (resources.requests if resources else None) or {}
        limits = (resources.limits if resources else None) or {}
        cpu_request += parse_quantity(requests.get("cpu"))
        mem_request += parse_quantity(requests.get("memory"))
        cpu_limit += parse_quantity(limits.get("cpu"))
        mem_limit += parse_quantity(limits.get("memory"))

    cpu, mem = usage.get(key, (0.0, 0.0))
    owners = meta.owner_references or []
    owner = f"{owners[0].kind}/{owners[0].name}" if owners else ""

    return Pod(
        namespace=meta.namespace,
        name=meta.name,
        node=spec.node_name or "",
        status=state,
        ready=f"{ready_count}/{total}",
        ready_fraction=(ready_count / total) if total else 0.0,
        restarts=restarts,
        cpu=cpu, mem=mem,
        cpu_request=cpu_request, mem_request=mem_request,
        cpu_limit=cpu_limit, mem_limit=mem_limit,
        created=meta.creation_timestamp,
        ip=(status.pod_ip if status else "") or "",
        qos=(status.qos_class if status else "") or "",
        containers=tuple(c.name for c in (spec.containers or [])),
        owner=owner,
        message=(message or "")[:200],
    )


def _convert_deployment(raw) -> Deployment:
    meta, spec, status = raw.metadata, raw.spec, raw.status
    strategy = spec.strategy.type if spec and spec.strategy else "RollingUpdate"
    return Deployment(
        namespace=meta.namespace or "-",
        name=meta.name or "-",
        ready=(status.ready_replicas if status else 0) or 0,
        replicas=(spec.replicas if spec else 0) or 0,
        updated=(status.updated_replicas if status else 0) or 0,
        available=(status.available_replicas if status else 0) or 0,
        unavailable=(status.unavailable_replicas if status else 0) or 0,
        strategy=strategy,
        created=meta.creation_timestamp,
    )


def _convert_event(raw) -> Event:
    involved = raw.involved_object
    last = raw.last_timestamp or raw.event_time or raw.first_timestamp
    return Event(
        namespace=raw.metadata.namespace or "-",
        name=(involved.name if involved else "-") or "-",
        kind=(involved.kind if involved else "-") or "-",
        reason=raw.reason or "-",
        type=raw.type or "-",
        message=(raw.message or "").replace("\n", " ")[:300],
        count=raw.count or 1,
        last=last,
    )


# --------------------------------------------------------------------------
# Demo cluster
# --------------------------------------------------------------------------
class DemoSource:
    """A synthetic cluster. Lets the interface be driven without a kubeconfig."""

    name = "demo"

    NAMESPACES = ("kube-system", "default", "observability", "ingress-nginx",
                  "starfleet-ops", "argocd", "data")
    APPS = {
        "kube-system": ["coredns", "kube-proxy", "metrics-server", "cilium"],
        "default": ["web-frontend", "checkout-api", "session-cache"],
        "observability": ["prometheus", "grafana", "loki", "otel-collector"],
        "ingress-nginx": ["ingress-nginx-controller"],
        "starfleet-ops": ["warp-core-controller", "sensor-array", "holodeck-sim"],
        "argocd": ["argocd-server", "argocd-repo-server", "argocd-application-controller"],
        "data": ["postgres", "kafka", "flink-taskmanager"],
    }

    def __init__(self, nodes: int = 6, seed: int = 1701):
        self.random = random.Random(seed)
        self.started = time.time()
        self.tick = 0
        self._nodes = []
        for index in range(nodes):
            role = "control-plane" if index < 3 else "worker"
            cores = 8.0 if role == "control-plane" else self.random.choice([16.0, 32.0])
            memory = cores * (4 * 2 ** 30)
            self._nodes.append(Node(
                name=f"ncc-1701-{'cp' if role == 'control-plane' else 'w'}{index:02d}",
                roles=role, version="v1.31.4", cpu_capacity=cores, mem_capacity=memory,
                pod_capacity=110, internal_ip=f"10.47.0.{10 + index}",
                created=datetime.now(timezone.utc), os_image="Ubuntu 24.04.1 LTS",
            ))
        self._pods: list[Pod] = []
        for namespace, apps in self.APPS.items():
            for app in apps:
                for replica in range(self.random.randint(1, 4)):
                    suffix = "".join(self.random.choice("bcdfghjkmnpqrstvwxz23456789")
                                     for _ in range(5))
                    node = self.random.choice(self._nodes)
                    self._pods.append(Pod(
                        namespace=namespace,
                        name=f"{app}-{self.random.randint(10000, 99999)}-{suffix}",
                        node=node.name, status="Running", ready="1/1",
                        ready_fraction=1.0,
                        cpu_request=self.random.choice([0.05, 0.1, 0.25, 0.5]),
                        mem_request=self.random.choice([64, 128, 256, 512]) * 2 ** 20,
                        created=datetime.now(timezone.utc), qos="Burstable",
                        containers=(app,), owner=f"ReplicaSet/{app}",
                        ip=f"10.244.{self.random.randint(0, 5)}.{self.random.randint(2, 250)}",
                    ))
        # A little drama so the colour ramps and status column have something
        # to show.
        for pod in self.random.sample(self._pods, 3):
            pod.status, pod.ready, pod.ready_fraction = "CrashLoopBackOff", "0/1", 0.0
            pod.restarts = self.random.randint(4, 87)
            pod.message = "back-off 5m0s restarting failed container"
        for pod in self.random.sample(self._pods, 2):
            pod.status, pod.ready, pod.ready_fraction = "Pending", "0/1", 0.0
            pod.node = ""
        self._deployments = []
        for namespace, apps in self.APPS.items():
            for app in apps:
                replicas = sum(
                    1 for pod in self._pods
                    if pod.namespace == namespace and pod.name.startswith(f"{app}-")
                )
                self._deployments.append(Deployment(
                    namespace=namespace,
                    name=app,
                    ready=replicas,
                    replicas=replicas,
                    updated=replicas,
                    available=replicas,
                    created=datetime.now(timezone.utc),
                ))
        self._birth = time.time()

    def snapshot(self, want_events: bool = False) -> Snapshot:
        self.tick += 1
        now = datetime.now(timezone.utc)
        elapsed = time.time() - self._birth

        snap = Snapshot(context="demo@enterprise", server_version="v1.31.4 (demo)",
                        metrics_available=True)
        for index, node in enumerate(self._nodes):
            wave = math.sin(elapsed / (7 + index * 2) + index) * 0.22
            base = 0.34 + index * 0.06 + wave + self.random.uniform(-0.05, 0.08)
            node.cpu_used = max(0.02, min(0.97, base)) * node.cpu_capacity
            memory_wave = math.sin(elapsed / (23 + index * 3)) * 0.1
            node.mem_used = max(0.1, min(0.95, 0.44 + index * 0.05 + memory_wave)) * node.mem_capacity
            node.ready = True
            node.condition = "Ready"
            node.created = datetime.fromtimestamp(self.started - 86400 * 37, timezone.utc)
            node.pod_count = 0
            snap.nodes.append(node)

        by_name = {node.name: node for node in self._nodes}
        for pod in self._pods:
            age_seed = (hash(pod.name) % 900000)
            pod.created = datetime.fromtimestamp(self.started - age_seed, timezone.utc)
            if pod.status == "Running":
                jitter = self.random.uniform(0.4, 1.9)
                pod.cpu = pod.cpu_request * jitter
                pod.mem = pod.mem_request * self.random.uniform(0.5, 1.6)
            else:
                pod.cpu = pod.mem = 0.0
            if pod.node in by_name:
                by_name[pod.node].pod_count += 1
            snap.pods.append(pod)

        for deployment in self._deployments:
            pods = [pod for pod in self._pods
                    if pod.namespace == deployment.namespace
                    and pod.name.startswith(f"{deployment.name}-")]
            deployment.ready = sum(1 for pod in pods if pod.healthy)
            deployment.updated = len(pods)
            deployment.available = deployment.ready
            deployment.unavailable = max(0, deployment.replicas - deployment.ready)
            deployment.created = datetime.fromtimestamp(
                self.started - hash(deployment.name) % 900000, timezone.utc)
            snap.deployments.append(deployment)
        snap.deployments.sort(
            key=lambda deployment: (deployment.name, deployment.namespace))

        snap.namespaces = sorted(
            {pod.namespace for pod in snap.pods}
            | {deployment.namespace for deployment in snap.deployments}
        )
        if want_events:
            reasons = [("Warning", "BackOff"), ("Normal", "Scheduled"),
                       ("Normal", "Pulled"), ("Warning", "FailedMount"),
                       ("Normal", "Started"), ("Warning", "Unhealthy")]
            for index in range(24):
                pod = self._pods[(self.tick + index) % len(self._pods)]
                kind, reason = reasons[index % len(reasons)]
                snap.events.append(Event(
                    namespace=pod.namespace, name=pod.name, kind="Pod",
                    reason=reason, type=kind,
                    message=f"{reason} for container {pod.containers[0]}",
                    count=self.random.randint(1, 12),
                    last=datetime.fromtimestamp(time.time() - index * 37, timezone.utc),
                ))
        return snap

    def delete_pod(self, namespace: str, name: str, grace: int | None = None) -> str:
        for index, pod in enumerate(self._pods):
            if pod.namespace == namespace and pod.name == name:
                pod.status = "Terminating"
                return f"DELETE SIMULATED · {namespace}/{name}"
        return "POD NOT FOUND"

    def pod_logs(self, namespace: str, name: str, container: str | None = None,
                 tail: int = 400, previous: bool = False) -> str:
        lines = []
        for index in range(min(tail, 60)):
            when = datetime.fromtimestamp(time.time() - (60 - index) * 3, timezone.utc)
            lines.append(f"{when.isoformat(timespec='seconds')} "
                         f"level=info msg=\"handled request\" path=/healthz "
                         f"status=200 duration={self.random.randint(1, 90)}ms")
        return "\n".join(lines)


    def describe_pod(self, namespace: str, name: str) -> dict:
        for pod in self._pods:
            if pod.namespace == namespace and pod.name == name:
                return {
                    "metadata": {"name": pod.name, "namespace": pod.namespace,
                                 "ownerReferences": [{"kind": "ReplicaSet"}]},
                    "spec": {"nodeName": pod.node,
                             "containers": [{"name": c} for c in pod.containers]},
                    "status": {"phase": pod.status, "podIP": pod.ip,
                               "qosClass": pod.qos},
                }
        return {}
