"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lcars-k8s",
        description="An LCARS-styled graphical and terminal dashboard for Kubernetes.")
    parser.add_argument("--demo", action="store_true",
                        help="run against a synthetic cluster, no kubeconfig needed")
    parser.add_argument("--kubeconfig", default=os.environ.get("KUBECONFIG"),
                        help="path to a kubeconfig file")
    parser.add_argument("--context", default=None, help="kubeconfig context to use")
    parser.add_argument("-n", "--namespace", default="",
                        help="start filtered to one namespace")
    parser.add_argument("-i", "--interval", type=float, default=2.0,
                        help="seconds between scans (default: 2)")
    parser.add_argument(
        "--view",
        choices=("pods", "nodes", "events", "deployments", "2", "3", "4", "5"),
        default="pods", help="view to open on (default: pods)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="apiserver request timeout in seconds (default: 10)")
    display = parser.add_argument_group("display")
    renderer = display.add_mutually_exclusive_group()
    renderer.add_argument(
        "--graphics", action="store_true",
        help="run the pixel-rendered SDL interface in an Xorg kiosk")
    renderer.add_argument(
        "--kmscon", action="store_true",
        help="enable Kmscon 256-colour output and full Unicode geometry")
    renderer.add_argument(
        "--fbterm", action="store_true",
        help="enable FbTerm 256-colour output and full Unicode geometry")
    display.add_argument(
        "--windowed", action="store_true",
        help="run graphical mode in a resizable desktop window")
    display.add_argument(
        "--direct-kms", action="store_true",
        help="use SDL KMSDRM directly instead of the recommended Xorg kiosk")
    display.add_argument(
        "--resolution", metavar="WIDTHxHEIGHT",
        help="graphical output resolution (default: current display)")
    display.add_argument(
        "--sidebar", choices=("left", "right"), default="left",
        help="place the navigation sidebar on the left or right (default: left)")
    display.add_argument(
        "--no-graphs", action="store_true",
        help="start with the CPU and memory graphs hidden")
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
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(raw_args)
    args.view = {"2": "pods", "3": "nodes", "4": "events",
                 "5": "deployments"}.get(args.view, args.view)

    if args.kmscon:
        os.environ["TERM"] = "xterm-256color"
    elif args.fbterm:
        os.environ["TERM"] = "fbterm"

    from . import glyphs, palette

    mode = "kmscon" if args.kmscon else ("fbterm" if args.fbterm else (
        palette.detect_mode() if args.colors == "auto" else (
            "console" if args.colors == "console" else "colour")))
    palette.set_mode(mode)
    glyphs.set_glyphs(
        ("solid" if mode == "console" else "braille")
        if args.glyphs == "auto" else args.glyphs)

    x11_child = os.environ.get("LCARS_X11_CHILD") == "1"
    if args.graphics and not args.windowed and not args.direct_kms and not x11_child:
        xinit = shutil.which("xinit")
        if xinit is None:
            print("lcars-k8s: xinit is required for graphical console mode.",
                  file=sys.stderr)
            print("Install it with: sudo apt install xinit xserver-xorg-core",
                  file=sys.stderr)
            return 2
        os.environ.pop("DISPLAY", None)
        os.environ.pop("WAYLAND_DISPLAY", None)
        os.environ["SDL_VIDEODRIVER"] = "x11"
        os.environ["LCARS_X11_CHILD"] = "1"
        server = [":1", "-keeptty", "-nolisten", "tcp"]
        try:
            tty = os.ttyname(sys.stdin.fileno())
            if tty.startswith("/dev/tty"):
                server.insert(1, f"vt{tty.removeprefix('/dev/tty')}")
        except OSError:
            pass
        print("lcars-k8s: launching fullscreen Xorg kiosk", file=sys.stderr)
        command = [xinit, sys.executable, "-m", "lcarsk8s", *raw_args,
                   "--", *server]
        os.execvp(xinit, command)

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

    if args.graphics:
        if args.direct_kms:
            os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        resolution = None
        if args.resolution:
            try:
                width, height = args.resolution.lower().split("x", 1)
                resolution = int(width), int(height)
            except (TypeError, ValueError):
                print("lcars-k8s: resolution must look like 1920x1080", file=sys.stderr)
                return 2
        try:
            from .graphics import LcarsGraphics
            return LcarsGraphics(
                source, interval=max(0.5, args.interval),
                namespace=args.namespace, view=args.view,
                windowed=args.windowed, resolution=resolution,
                sidebar=args.sidebar, show_graphs=not args.no_graphs).run()
        except Exception as error:
            print(f"lcars-k8s: graphical display failed: {error}", file=sys.stderr)
            print("Switch away from Kmscon before direct KMS/DRM mode, or use "
                  "--windowed under a desktop session.", file=sys.stderr)
            return 2

    from .app import LcarsK8s

    app = LcarsK8s(source, interval=max(0.5, args.interval),
                   namespace=args.namespace, view=args.view,
                   sidebar=args.sidebar, show_graphs=not args.no_graphs)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
