"""Dev helper: drive the app headlessly and capture screenshots as PNGs."""
import asyncio, sys
import cairosvg
from lcarsk8s import palette, glyphs

MODE = "console" if "--console" in sys.argv else (
    "kmscon" if "--kmscon" in sys.argv else (
        "fbterm" if "--fbterm" in sys.argv else "colour"))
palette.set_mode(MODE)
glyphs.set_glyphs(next((a.split("=")[1] for a in sys.argv if a.startswith("--glyphs=")),
                        "solid" if MODE == "console" else "braille"))

from lcarsk8s.app import LcarsK8s
from lcarsk8s.cluster import DemoSource


async def main(width=180, height=50, keys=(), name="shot"):
    source = DemoSource()
    app = LcarsK8s(source, interval=60.0)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        for _ in range(140):
            source._birth -= 0.7
            app.ingest(source.snapshot(want_events=True))
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    path = f"/tmp/{name}"
    open(path + ".svg", "w").write(svg)
    cairosvg.svg2png(url=path + ".svg", write_to=path + ".png", scale=1.0,
                     background_color="#000000")
    print(path + ".png")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]
            if a not in ("--console", "--kmscon", "--fbterm")
            and not a.startswith("--glyphs=")]
    name = argv[0] if argv else "shot"
    w, h = (int(x) for x in (argv[1].split("x") if len(argv) > 1 else ["180", "50"]))
    asyncio.run(main(width=w, height=h, keys=argv[2:], name=name))
