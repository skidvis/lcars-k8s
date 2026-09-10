import asyncio
from lcarsk8s.app import LcarsK8s
from lcarsk8s.cluster import DemoSource
async def main():
    src = DemoSource(); app = LcarsK8s(src, interval=60.0)
    async with app.run_test(size=(160, 45)) as pilot:
        await pilot.pause(); app.ingest(src.snapshot(want_events=True)); await pilot.pause()
        for size in [(80,24),(100,30),(200,60),(70,20),(120,40)]:
            app._driver._size = size
            await pilot.resize_terminal(*size); await pilot.pause()
            app.ingest(src.snapshot(want_events=True)); await pilot.pause()
            await pilot.press("1"); await pilot.pause(); await pilot.press("1"); await pilot.pause()
            print(size, "sidebar:", app.query_one("LcarsSidebar").display,
                  "meters:", app.query_one("#meters").display)
    print("resize OK")
asyncio.run(main())
