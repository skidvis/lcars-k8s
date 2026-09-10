import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from lcarsk8s.cluster import DemoSource
from lcarsk8s.graphics import LcarsGraphics

source = DemoSource()
app = LcarsGraphics(source, interval=60, windowed=True, resolution=(1920, 1080))
for _ in range(120):
    source._birth -= 0.5
    app.snapshot = source.snapshot(want_events=True)
    app.history_cpu.append(app.snapshot.cpu_fraction)
    app.history_mem.append(app.snapshot.mem_fraction)
app.status = "SENSORS ONLINE"
app.draw()
path = "/tmp/lcars-k8s-graphics.png"
pygame.image.save(app.canvas, path)
app.executor.shutdown(wait=False, cancel_futures=True)
pygame.quit()
print(path)
