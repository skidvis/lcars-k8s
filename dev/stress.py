import asyncio, sys
from lcarsk8s import palette, glyphs
if "--console" in sys.argv:
    palette.set_mode("console"); glyphs.set_glyphs("block")
from lcarsk8s.app import LcarsK8s
from lcarsk8s.cluster import DemoSource

SEQ = ["3","4","5","2","tab","tab","n","n","a","slash","w","e","b","escape",
       "full_stop","full_stop","comma","r","1","1","space","space",
       "plus","minus","ctrl+r","down","down","d","m","escape","l","c","p","escape",
       "x","y","question_mark","escape","3","r","2","end","home"]

async def main():
    src = DemoSource(); app = LcarsK8s(src, interval=60.0)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        for _ in range(30):
            src._birth -= 0.7
            app.ingest(src.snapshot(want_events=True))
        await pilot.pause()
        for key in SEQ:
            await pilot.press(key)
            await pilot.pause()
            app.ingest(src.snapshot(want_events=True))
            await pilot.pause()
        print("OK — survived", len(SEQ), "keys; view:", app.view,
              "ns:", repr(app.namespace), "filter:", repr(app.filter_text),
              "sort:", app.sort_index, "paused:", app.paused,
              "status:", app.query_one("#footer").status)
asyncio.run(main())
