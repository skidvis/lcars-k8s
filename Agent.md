# Agent Troubleshooting Notes

## Purpose

Use this file to resume troubleshooting the pixel-rendered lcars-k8s dashboard on the target Ubuntu Server machine.

## Current Goal

Run the graphical 1920x1080 LCARS renderer fullscreen on the built-in laptop display without a desktop environment. Preserve the Textual renderer as the terminal fallback.

## Target System Facts

- Ubuntu Server 24.04 package generation
- Built-in laptop display
- Intel Alder Lake-P Iris Xe GPU using `i915`
- NVIDIA GeForce RTX 3080 Ti Laptop GPU using proprietary driver 570
- NVIDIA DRM modesetting reports `Y`
- Built-in display connector is Intel `eDP-1`
- NVIDIA connectors were disconnected during diagnosis
- DRM card numbers change after restarting the display stack, so never hardcode `card1` or `card2` without checking the current driver and connectors
- Kmscon 0.1.5
- wlroots 0.17.1
- pygame-ce 2.5.8 with SDL 2.32.10

## Current Code Architecture

- `lcarsk8s/cluster.py` is shared by both renderers
- `lcarsk8s/app.py` is the Textual renderer
- `lcarsk8s/graphics.py` is the pixel-rendered pygame renderer
- `lcarsk8s/cli.py` selects the renderer and launches its display host
- `lcarsk8s/assets/Antonio.ttf` is bundled for condensed LCARS typography
- `dev/graphics_preview.py` renders the graphical surface headlessly
- `dev/graphics_stress.py` exercises graphical key handling
- `preview-graphics.png` is the expected graphical composition

## Verified Application Behavior

- The graphical renderer creates the correct 1920x1080 frame under SDL's dummy driver
- The saved frame contains the LCARS interface
- Graphical keyboard stress test passed 28 events
- Textual keyboard stress test passed 42 events
- Terminal resize tests passed at 80x24, 100x30, 120x40, 200x60, and 70x20
- The built wheel contains `graphics.py`, `Antonio.ttf`, and the Antonio OFL license
- Ruff passes when the intentional broad worker-boundary catches are ignored with `BLE001`

## Failed Display Paths

### Raw SDL KMSDRM

Command form:

```bash
lcars-k8s --graphics --direct-kms
```

Observed result:

- Black screen
- Keyboard input not delivered
- Orphaned Python process could consume a full CPU core

Conclusion:

Raw pygame SDL KMSDRM is diagnostic-only. Do not make it the default.

### Cage with NVIDIA GLES2

Observed log:

```text
Failed to initialize EGL
Could not initialize EGL
Could not initialize EGL context
Could not initialize EGL
Failed to query renderer texture formats
Failed to create DRM backend
```

Relevant system fact:

- `libnvidia-gl-570` was not installed
- `libnvidia-egl-wayland1` was not installed
- NVIDIA package versions were mixed, with driver 570 and some utilities at 595

Conclusion:

The NVIDIA EGL and GBM userspace stack was incomplete.

### Cage with NVIDIA Pixman

Observed result:

```text
Failed to query renderer texture formats
Failed to create DRM backend
```

Conclusion:

wlroots Pixman could not obtain compatible scanout texture formats from the proprietary NVIDIA DRM device.

### Cage with Intel GLES2 and pygame Wayland

Cage successfully selected the connected Intel GPU and stayed alive. The pygame child also stayed alive but blocked inside:

```python
pygame.display.set_mode(...)
```

Observed log stopped at:

```text
lcars-k8s: Cage display /dev/dri/card1 driver=i915 renderer=gles2
pygame-ce 2.5.8 (SDL 2.32.10, Python 3.12.3)
lcars-k8s: creating SDL surface size=(1920, 1080) scaled=True
```

No line reporting `driver=wayland` appeared. No `/tmp/lcars-k8s-live-frame.png` was created. Process state was sleeping at low CPU.

The same block occurred with pygame's ordinary Wayland software surface and its `SCALED` surface.

Conclusion:

Cage, Intel DRM, libseat, and GLES2 were working. pygame-ce's Wayland display creation was the failing boundary on this machine.

## Background Launch Trap

Cage must not be tested as a background SSH job. Doing so produced:

```text
Could not open target tty: Permission denied
Timeout waiting session to become active
failed to start a session
```

The graphical host must be launched in the foreground from a locally logged-in active kernel VT. Redirection is fine, but appending `&` is not.

## Current Untested Fix

The newest code no longer uses Cage for normal graphical mode.

`lcars-k8s --graphics` now:

1. Requires `xinit`
2. Removes inherited `DISPLAY` and `WAYLAND_DISPLAY`
3. Sets `SDL_VIDEODRIVER=x11`
4. Marks the child with `LCARS_X11_CHILD=1`
5. Starts a private X server on display `:1`
6. Binds Xorg to the active kernel VT when it can resolve the current TTY
7. Passes `-keeptty -nolisten tcp` to Xorg
8. Runs pygame fullscreen through X11

This Xorg kiosk path has been unit-tested for command construction but has not yet been verified on the target physical machine.

## Next Test

Install the required Xorg kiosk packages:

```bash
sudo apt install xinit xserver-xorg-core
```

Stop prior display and dashboard processes:

```bash
pkill -TERM cage
pkill -TERM -f '/lcars-k8s/bin/python3 -m lcarsk8s'
```

From the active local kernel VT, in the foreground:

```bash
rm -f /tmp/lcars-graphics.log /tmp/lcars-k8s-live-frame.png
lcars-k8s --graphics --demo >/tmp/lcars-graphics.log 2>&1
```

Expected log sequence:

```text
lcars-k8s: launching fullscreen Xorg kiosk
lcars-k8s: creating SDL surface size=(0, 0) fullscreen=True
lcars-k8s: SDL (...) driver=x11 screen=(...)
lcars-k8s: first frame presented and saved to /tmp/lcars-k8s-live-frame.png
```

If Xorg fails, inspect:

```bash
cat /tmp/lcars-graphics.log
find "$HOME/.local/share/xorg" /var/log -maxdepth 2 -name 'Xorg*.log' -type f 2>/dev/null
```

Then read the newest Xorg log. Check VT ownership, GPU selection, device permissions, existing display locks, and whether Xorg selected the Intel modesetting driver.

## Process Cleanup

Black-screen failures may leave Cage or Python children alive. Inspect dynamically:

```bash
pgrep -af 'cage|Xorg|xinit|lcarsk8s|lcars-k8s'
```

Clean only the dashboard-related processes:

```bash
pkill -TERM cage
pkill -TERM -f '/lcars-k8s/bin/python3 -m lcarsk8s'
```

Do not kill an unrelated desktop Xorg server.

## Important Diagnostic Rules

- Always distinguish a fresh log from an earlier failed launch
- Always truncate or remove the log before a test
- Use absolute paths in probes when shell or home expansion is in doubt
- Verify the installed package contains the current diagnostic strings before assuming `./install.sh` used the newest source
- Check running process command lines rather than relying on remembered launch commands
- A movable pointer only proves the compositor started; it does not prove the pygame client created a surface
- A saved `/tmp/lcars-k8s-live-frame.png` proves drawing completed independently of display presentation
- State which claims are verified, which are inferred, and which path remains untested

## Bundle

The graphical release archive is named `lcars-k8s-1.0.0-graphics.tar.gz` and is
created beside the project directory. Verify the current archive with
`sha256sum` after every rebuild.
