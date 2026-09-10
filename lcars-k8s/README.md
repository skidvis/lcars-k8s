# lcars-k8s

A terminal dashboard for Kubernetes that works the way btop works and looks the
way LCARS looks.

Cluster CPU and memory scroll past as braille history graphs with a meter for
every node beside them, where btop puts its per-core meters. The pod list is
btop's process list: sort it, filter it, watch it update in place, and kill
things from it. The chrome is LCARS — elbows, chamfered pills, black caps-lock
labels on coloured strips, and reference numbers that mean nothing at all.

Runs on Ubuntu Server over SSH. Adapts down to an 80x24 window.

## Install

```bash
./install.sh
```

That builds a virtualenv under `~/.local/share/lcars-k8s` and links the
`lcars-k8s` command into `~/.local/bin`. Nothing lands in your system Python.

If you already use pipx, that works too:

```bash
pipx install .
```

Requires Python 3.10 or newer, which covers Ubuntu 22.04 and 24.04 out of the
box. The only dependencies are `textual` and the official `kubernetes` client.

## Use

```bash
lcars-k8s                     # current kubeconfig context
lcars-k8s --context prod      # a specific context
lcars-k8s -n kube-system      # start scoped to one namespace
lcars-k8s -i 5                # scan every 5 seconds instead of 2
lcars-k8s --view nodes        # open on a different view
lcars-k8s --demo              # synthetic cluster, no kubeconfig needed
```

Try `--demo` first. It generates a plausible cluster with drifting load and a
few pods in CrashLoopBackOff, so you can see what everything does before
pointing it at anything real.

Inside a pod it picks up the in-cluster service account automatically.

## Keys

| | |
|---|---|
| `1` | show or hide the cluster graphs |
| `2` `3` `4` | pods · nodes · events |
| `TAB` | cycle the views |
| `n` / `a` | step through namespaces / show all |
| `/` or `f` | filter by name, namespace, node or status |
| `ESC` | clear the filter |
| `<` `>` | move the sort column |
| `r` | reverse the sort |
| `l` | tail the container log |
| `d` | pod detail, then `m` for the manifest |
| `x` or `DEL` | delete the pod, with confirmation |
| `SPACE` | hold and resume scanning |
| `+` `-` | slower or faster scan interval |
| `CTRL+R` | scan once, now |
| `?` | the same list, in the app |
| `q` | quit |

The sidebar and the pod table's column headers respond to the mouse.

## Reading the panels

The graphs hold roughly two screen-widths of history, newest sample at the
right edge. Colour tracks load throughout — periwinkle when quiet, through
lilac and orange, into red as things saturate.

`CPU%` and `MEM%` on a pod are its share of its own limit. Where no limit is
set, they fall back to its share of the node it landed on, which is the number
that actually predicts trouble.

If metrics-server isn't installed, the meters switch to summed resource
requests and the stat strip says so in red. Allocation instead of usage — still
true, just answering a different question.

## Permissions

`rbac.yaml` has the minimum: get and list on nodes, pods, events and
namespaces, get on pod logs, delete on pods, and read access to
`metrics.k8s.io`. Drop the delete rule for a read-only console; `x` will then
report the permission error instead of removing anything.

## If it comes out red

On the Linux virtual console — the physical screen attached to the machine,
not an SSH session — you get sixteen colours and a font with no braille.
LCARS orange (`#FF9900`) rounds to the nearest of those sixteen, and by RGB
distance that is **bright red**, so the whole interface turns into a red
alert. The graphs come out as rows of diamonds for the same reason: the
console font has nothing at U+2800, so it substitutes.

The app detects `TERM=linux` and switches to console mode by itself: ANSI
colours chosen by hand rather than rounded to, and filled-area graphs instead
of braille dots. Blockier, but recognisably LCARS.

Console fonts are stingier than they look. Most carry the full block `U+2588`
and nothing else from that range, so half blocks, shade blocks and the
half-width bar caps all come out as substitution lozenges. That's what
`--glyphs solid` is for, and it is what console mode picks:

| `--glyphs` | uses | for |
|---|---|---|
| `braille` | dots, quadrants, eighth blocks | a real terminal font |
| `block` | half and shade blocks, bar caps | 16-colour terminals with decent fonts |
| `solid` | the full block, nothing else | the Linux virtual console |
| `ascii` | `#` and `.` | anything at all |

```bash
lcars-k8s --colors console      # 16-colour palette, solid graphs
lcars-k8s --colors full         # the real palette, whatever $TERM claims
lcars-k8s --glyphs solid        # if you see diamonds where blocks should be
```

`--colors` and `--glyphs` are independent, so a 16-colour terminal that *does*
have a good font can run `--colors console --glyphs braille`.

The best-looking option is still to leave the console alone and SSH in from a
desktop terminal, where the full palette is available.

## Terminal requirements

- **Truecolor**, for the real palette. Most modern terminals have it; if yours
  looks flat, set `COLORTERM=truecolor`. Without it, see the section above.
- **A font with braille and block glyphs**, for the btop-style graphs. DejaVu
  Sans Mono (already on Ubuntu), JetBrains Mono, Fira Code and any Nerd Font
  all work. `--glyphs block` covers everything else.
- **80x24 minimum.** The sidebar hides below 92 columns and the graphs shrink,
  then disappear, as height gets tight. 120x40 is comfortable.

Over SSH with `screen` or `tmux`, set `TERM=xterm-256color` before starting.

## Troubleshooting

**"No usable kubeconfig and not running inside a pod"** — set `KUBECONFIG` or
pass `--kubeconfig`. On k3s the file is at `/etc/rancher/k3s/k3s.yaml` and
needs root or a copy you own.

**"node metrics unavailable"** in the status bar — metrics-server isn't
installed, or isn't ready. `kubectl top nodes` will fail the same way. The
dashboard keeps working on requests in the meantime.

**Large clusters feel sluggish** — every scan lists all pods. Raise the
interval with `-i 10`, or scope to a namespace with `-n`. Polling happens on a
worker thread, so the interface stays responsive either way.

## Layout of the code

| | |
|---|---|
| `palette.py` | the LCARS colours, both palettes, and the gradient ramps |
| `glyphs.py` | braille graphs, meters, elbows, pills, panel bars |
| `cluster.py` | the API-server data layer, plus the demo source |
| `widgets.py` | header, sidebar, load panels, footer |
| `screens.py` | help, logs, detail and confirmation modals |
| `app.py` | layout, keys, sorting, polling |

The drawing primitives in `glyphs.py` don't know anything about Kubernetes, and
`cluster.py` doesn't know anything about the terminal. Adding a view means a
table and a key binding.

MIT licensed.
