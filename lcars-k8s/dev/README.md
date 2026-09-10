# Development helpers

These drive the app headlessly, which is how it was built and checked.

    python3 dev/preview.py shot 150x42          # render to /tmp/shot.png
    python3 dev/preview.py kms 180x50 --kmscon # render the Kmscon profile
    python3 dev/preview.py fb 180x50 --fbterm   # render the FbTerm profile
    python3 dev/preview.py logs 150x42 l        # press keys first, then capture
    python3 dev/graphics_preview.py             # render the 1920x1080 SDL surface
    python3 dev/graphics_stress.py              # exercise graphical key handling
    python3 dev/stress.py                       # walk every terminal key binding
    python3 dev/resize.py                       # check the terminal responsive layout

`preview.py` needs `cairosvg` (`pip install cairosvg`). Note that the SVG
rasteriser collapses runs of spaces and overhangs block glyphs, so use
`render_line()` output rather than the PNG when checking exact alignment.
