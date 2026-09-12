import unittest

from lcarsk8s.cluster import parse_network_logs


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


if __name__ == "__main__":
    unittest.main()
