"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lcars-k8s",
        description="An LCARS-styled terminal dashboard for Kubernetes.")
    parser.add_argument("--demo", action="store_true",
                        help="run against a synthetic cluster, no kubeconfig needed")
    parser.add_argument("--kubeconfig", default=os.environ.get("KUBECONFIG"),
                        help="path to a kubeconfig file")
    parser.add_argument("--context", default=None, help="kubeconfig context to use")
    parser.add_argument("-n", "--namespace", default="",
                        help="start filtered to one namespace")
    parser.add_argument("-i", "--interval", type=float, default=2.0,
                        help="seconds between scans (default: 2)")
    parser.add_argument("--view", choices=("pods", "nodes", "events"), default="pods",
                        help="view to open on (default: pods)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="apiserver request timeout in seconds (default: 10)")
    display = parser.add_argument_group("display")
    display.add_argument(
        "--colors", "--colours", dest="colors",
        choices=("auto", "full", "console"), default="auto",
        help="'full' uses the 24-bit LCARS palette; 'console' picks 16-colour "
             "ANSI equivalents by hand, for the Linux virtual console "
             "(default: auto, from $TERM)")
    display.add_argument(
        "--glyphs", choices=("auto", "braille", "block", "solid", "ascii"), default="auto",
        help="'braille' draws btop-style dot graphs and chamfered corners; "
             "'block' uses half and shade blocks; 'solid' uses the full block "
             "and nothing else, for Linux console fonts; 'ascii' assumes "
             "nothing (default: auto, follows --colors)")
    parser.add_argument("--version", action="version", version=f"lcars-k8s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # The palette has to be chosen before the app module is imported, because
    # its stylesheet is built from the palette at import time.
    from . import glyphs, palette

    mode = palette.detect_mode() if args.colors == "auto" else (
        "console" if args.colors == "console" else "colour")
    palette.set_mode(mode)
    glyphs.set_glyphs(
        ("solid" if mode == "console" else "braille")
        if args.glyphs == "auto" else args.glyphs)

    from .cluster import ClusterError, DemoSource, KubeSource

    if args.demo:
        source = DemoSource()
    else:
        try:
            source = KubeSource(kubeconfig=args.kubeconfig, context=args.context,
                                timeout=args.timeout)
        except ClusterError as error:
            print(f"lcars-k8s: {error}", file=sys.stderr)
            print("Try --demo to see the interface without a cluster.",
                  file=sys.stderr)
            return 2

    from .app import LcarsK8s

    app = LcarsK8s(source, interval=max(0.5, args.interval),
                   namespace=args.namespace, view=args.view)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
