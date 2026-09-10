# Development helpers

These drive the app headlessly, which is how it was built and checked.

    python3 dev/preview.py shot 150x42        # render to /tmp/shot.png
    python3 dev/preview.py logs 150x42 l      # press keys first, then capture
    python3 dev/stress.py                     # walk every key binding
    python3 dev/resize.py                     # check the responsive layout

`preview.py` needs `cairosvg` (`pip install cairosvg`). Note that the SVG
rasteriser collapses runs of spaces and overhangs block glyphs, so use
`render_line()` output rather than the PNG when checking exact alignment.
