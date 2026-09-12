import unittest

from lcarsk8s.cli import build_parser


class CliTests(unittest.TestCase):
    def test_default_interval_is_five_seconds(self):
        self.assertEqual(build_parser().parse_args([]).interval, 5.0)

    def test_interval_can_be_overridden(self):
        self.assertEqual(build_parser().parse_args(["--interval", "2"]).interval, 2.0)


if __name__ == "__main__":
    unittest.main()
