import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from lcarsk8s.cluster import DemoSource
from lcarsk8s.graphics import LcarsGraphics

source = DemoSource()
app = LcarsGraphics(source, interval=60, windowed=True, resolution=(1280, 720))
app.snapshot = source.snapshot(want_events=True)
keys = [pygame.K_3, pygame.K_4, pygame.K_2, pygame.K_TAB, pygame.K_TAB,
        pygame.K_n, pygame.K_a, pygame.K_SLASH, pygame.K_w, pygame.K_ESCAPE,
        pygame.K_PERIOD, pygame.K_COMMA, pygame.K_r, pygame.K_1, pygame.K_1,
        pygame.K_SPACE, pygame.K_SPACE, pygame.K_PLUS, pygame.K_MINUS,
        pygame.K_DOWN, pygame.K_DOWN, pygame.K_HOME, pygame.K_END,
        pygame.K_HOME, pygame.K_2, pygame.K_d]
for key in keys:
    unicode = "w" if key == pygame.K_w else ""
    app._key(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode))
app.action_future.result(timeout=5)
app._collect()
assert app.modal == "text"
app._key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
app._key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l, unicode=""))
app.action_future.result(timeout=5)
app._collect()
assert app.modal == "text"
app.draw()
app.executor.shutdown(wait=False, cancel_futures=True)
pygame.quit()
print(f"graphics OK: {len(keys) + 2} keys, view={app.view}, rows={len(app._rows())}")
