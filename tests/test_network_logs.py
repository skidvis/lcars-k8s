import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

from lcarsk8s.cluster import (HitCounter, KubeSource, NetworkLog, ingress_hit_counts,
                              parse_network_logs)


class ParseNetworkLogsTests(unittest.TestCase):
    def test_parses_default_ingress_nginx_access_log(self):
        raw = (
            '10.0.0.1 - - [12/Sep/2026:03:12:00 +0000] '
            '"GET /api/orders?id=2 HTTP/1.1" 200 42 "-" "curl/8.0" '
            '123 0.004 [default-orders-80] [] 10.0.1.2:8080 42 0.003 200 abc123'
        )

        entries = parse_network_logs(raw)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].time, "12/Sep/2026:03:12:00 +0000")
        self.assertEqual(entries[0].status, 200)
        self.assertEqual(entries[0].ingress, "default-orders-80")
        self.assertEqual(entries[0].path, "/api/orders?id=2")
        self.assertEqual(entries[0].ip, "10.0.0.1")

    def test_parses_live_ingress_json_format(self):
        raw = (
            '{"time":"2026-09-12T04:03:33+00:00","ip":"172.16.46.24",'
            '"method":"GET","path":"/wp-admin/install.php","status":404,'
            '"bytes":4333,"rt":0.003,"ingress":"default-www-depletement-com-80",'
            '"upstream":"172.16.228.125:4321","ustatus":"404","urt":"0.003"}'
        )

        entries = parse_network_logs(raw)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].time, "2026-09-12T04:03:33+00:00")
        self.assertEqual(entries[0].status, 404)
        self.assertEqual(entries[0].ingress, "default-www-depletement-com-80")
        self.assertEqual(entries[0].path, "/wp-admin/install.php")
        self.assertEqual(entries[0].ip, "172.16.46.24")

    def test_parses_stringified_bytes_from_kubernetes_client(self):
        raw = repr(
            b'{"time":"2026-09-12T04:03:35+00:00","path":"/about/",'
            b'"status":200,"ingress":"default-www-sharkjets-com-80"}\n'
            b'{"time":"2026-09-12T04:03:39+00:00","path":"/blog/",'
            b'"status":200,"ingress":"default-www-puertoricancookbooks-com-80"}'
        )

        entries = parse_network_logs(raw)

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].path, "/about/")
        self.assertEqual(entries[1].path, "/blog/")

    def test_parses_common_json_field_names(self):
        raw = (
            '{"time_iso8601":"2026-09-12T03:12:00+00:00",'
            '"status":"404","ingress_name":"orders-ingress",'
            '"request_uri":"/missing"}'
        )

        entries = parse_network_logs(raw)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].time, "2026-09-12T03:12:00+00:00")
        self.assertEqual(entries[0].status, 404)
        self.assertEqual(entries[0].ingress, "orders-ingress")
        self.assertEqual(entries[0].path, "/missing")

    def test_uses_request_when_json_path_is_absent(self):
        raw = '{"time":"now","status":201,"request":"POST /login HTTP/2.0"}'

        entries = parse_network_logs(raw)

        self.assertEqual(entries[0].path, "/login")

    def test_skips_unrecognized_lines(self):
        self.assertEqual(parse_network_logs("startup notice\nnot an access log"), [])


class NetworkHistoryTests(unittest.TestCase):
    def test_appends_deduplicates_and_retains_entries(self):
        first = '{"time":"2026-09-12T04:03:35+00:00","path":"/a","status":200,"id":"a"}'
        second = '\n'.join((
            first,
            '{"time":"2026-09-12T04:03:36+00:00","path":"/b","status":200,"id":"b"}',
        ))

        class Core:
            responses = iter((first, second, ""))

            def read_namespaced_pod_log(self, **kwargs):
                return next(self.responses)

        pod = SimpleNamespace(
            metadata=SimpleNamespace(
                name="ingress-nginx-controller-test",
                namespace="ingress",
                labels={},
            ),
            spec=SimpleNamespace(containers=[SimpleNamespace(name="controller")]),
        )
        source = KubeSource.__new__(KubeSource)
        source.core = Core()
        source.timeout = 10
        source._network_history = {}

        first_entries, _ = source.network_log_entries([pod])
        second_entries, _ = source.network_log_entries([pod])
        retained_entries, _ = source.network_log_entries([pod])

        self.assertEqual([entry.identity for entry in first_entries], ["a"])
        self.assertEqual([entry.identity for entry in second_entries], ["b", "a"])
        self.assertEqual([entry.identity for entry in retained_entries], ["b", "a"])


class IngressHitCountTests(unittest.TestCase):
    def test_totals_per_ingress_without_excluded_requests(self):
        hits = {("default-x-com-80", "/"): 200, ("default-x-com-80", "/healthz"): 900,
                ("default-y-com-80", "/api"): 34, ("monitoring-grafana-80", "/"): 50}
        self.assertEqual(ingress_hit_counts(hits, ("/healthz", "grafana")),
                         [("default-x-com-80", 200), ("default-y-com-80", 34)])
        self.assertEqual(ingress_hit_counts(hits)[0], ("default-x-com-80", 1100))


class HitCounterTests(unittest.TestCase):
    def test_counts_each_request_once_rolls_off_after_24h_and_persists(self):
        now = 1_800_000_000.0  # 2027-01-15T08:00:00Z

        def log(seconds_ago, path, ident):
            when = datetime.fromtimestamp(now - seconds_ago, timezone.utc)
            return NetworkLog(when.isoformat(timespec="seconds"), 200, "default-x-com-80",
                              path, ident)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "hits.json"
            counter = HitCounter(path)
            self.assertEqual(counter.since_seconds(now), 86400)
            counter.add([log(90000, "/", "too-old"), log(3600, "/?page=2", "a"),
                         log(30, "/healthz", "b")], now)
            counter.commit(now)
            counter.add([log(30, "/healthz", "b"), log(5, "/healthz", "c")], now + 60)
            counter.commit(now + 60)
            self.assertEqual(counter.totals(), {("default-x-com-80", "/"): 1,
                                                ("default-x-com-80", "/healthz"): 2})

            reloaded = HitCounter(path)
            self.assertEqual(reloaded.totals(), counter.totals())
            self.assertEqual(reloaded.since_seconds(now + 120), 70)
            reloaded.commit(now + 3600 + 86400)
            self.assertEqual(reloaded.totals(), {})


if __name__ == "__main__":
    unittest.main()
