---
name: lcars-k8s
description: A pixel-rendered LCARS operations console for Kubernetes
colors:
  space-black: "#000000"
  panel-black: "#0A080F"
  command-amber: "#FF9900"
  structural-peach: "#FF9966"
  data-gold: "#FFCC00"
  warm-text: "#FFCC99"
  structural-lavender: "#CC99CC"
  data-periwinkle: "#9999FF"
  telemetry-ice: "#99CCFF"
  alert-mars: "#CC4444"
  secondary-grey: "#5C5C7A"
typography:
  display:
    fontFamily: "Antonio, DejaVu Sans, sans-serif"
    fontSize: "46px at 1920x1080"
    fontWeight: 500
    lineHeight: 1
  body:
    fontFamily: "Antonio, DejaVu Sans, sans-serif"
    fontSize: "22px at 1920x1080"
    fontWeight: 400
    lineHeight: 1.15
  label:
    fontFamily: "Antonio, DejaVu Sans, sans-serif"
    fontSize: "25px at 1920x1080"
    fontWeight: 600
    lineHeight: 1
rounded:
  pill: "999px"
  modal: "34px"
spacing:
  cell: "8px"
  panel: "24px"
components:
  command-block:
    backgroundColor: "{colors.command-amber}"
    textColor: "{colors.space-black}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    height: "62px"
  panel-header:
    backgroundColor: "{colors.command-amber}"
    textColor: "{colors.space-black}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    height: "38px"
---

# Design System: lcars-k8s

## Overview

**Creative North Star: "The Working Okudagram"**

This is a functional Kubernetes control surface shaped from the grammar of a physical LCARS panel. It uses connected concave elbows, long asymmetric rails, colored block sequences, black data wells, condensed uppercase labels, and flat backlit color. The interface should read as LCARS at a distance and as a serious operations console up close.

The primary scene is a fullscreen 1920x1080 display attached directly to an Ubuntu server. SDL renders the composition through a private fullscreen Xorg kiosk started from the active kernel VT, without a desktop environment or terminal cell grid. A separate Textual renderer preserves access through Kmscon, FbTerm, the kernel console, and SSH.

**Key Characteristics:**
- Pixel-rendered top and bottom frame assemblies
- An asymmetric left command spine
- Warm structure, cool telemetry, and lavender secondary structure
- Black data wells with dense aligned values
- Condensed LCARS lettering from the bundled Antonio typeface
- Decorative reference codes used sparingly

## Colors

Warm colors build the frame, cool colors carry healthy telemetry, lavender marks secondary structure, and red appears only for actual problems.

### Primary
- **Command Amber:** Main top structure, active panel headers, and primary command blocks.
- **Structural Peach:** Secondary warm frame segments and the top elbow.
- **Data Gold:** Warnings, sorting state, and emphasized operational values.

### Secondary
- **Structural Lavender:** Bottom framing, secondary navigation, and held states.
- **Data Periwinkle:** Low utilization and secondary workload data.
- **Telemetry Ice:** Healthy state, ready counts, and current context.

### Tertiary
- **Alert Mars:** Failures, destructive confirmation, and red-alert conditions only.

### Neutral
- **Space Black:** Non-negotiable canvas and the negative space that shapes every panel.
- **Panel Black:** Slightly lifted graph and modal wells.
- **Warm Text:** Primary readable text.
- **Secondary Grey:** Supporting labels and inactive metadata.

**The Red Alert Rule.** Red never decorates the normal interface. It reports a real warning, failure, destructive action, or critical load.

## Typography

**Display Font:** Antonio
**Body Font:** Antonio
**Fallback Font:** DejaVu Sans

**Character:** Tall, condensed lettering echoes the Swiss 911 character of production LCARS panels while leaving enough horizontal room for Kubernetes identifiers. Size, weight, color fields, and alignment create a clear hierarchy.

### Hierarchy
- **Display:** Large telemetry values inside graph wells.
- **Title:** Uppercase system and panel titles.
- **Body:** Mixed-case Kubernetes identifiers and values.
- **Label:** Uppercase text knocked out of colored structural fields.

**The Operational Case Rule.** LCARS interface labels are uppercase, while Kubernetes resource names and log content preserve their real case.

## Layout

The graphical renderer uses a fixed 1920x1080 design canvas and scales it proportionally to the active display. A left command spine joins the top and bottom frame assemblies. The main area contains paired telemetry wells, a workload tally, and one dominant table. Overlays keep the same surrounding frame so operational context never disappears. The terminal renderer independently adapts to 80x24.

## Elevation & Depth

There are no shadows, glass surfaces, or simulated raised controls. Depth comes from flat colored structure against absolute black, interruptions in long rails, graph fills, and the contrast between the frame and data wells.

**The Flat Panel Rule.** Every surface must remain credible as printed, backlit console artwork.

## Shapes

Real antialiased geometry replaces terminal glyph approximations. Concave elbows join the command spine to horizontal rails. Exposed bars terminate in semicircular pill caps. Sidebar controls have flat connected edges and rounded exposed edges. Black gaps remain deliberate and consistent.

## Components

### Command Blocks
- **Shape:** Horizontal 62px pills connected visually to the left spine.
- **Primary:** Black uppercase text on amber, peach, lavender, or periwinkle.
- **Active:** Longer silhouette and stronger warm color.

### Data Wells
- **Background:** Panel Black.
- **Structure:** A 38px colored title rail followed by a graph, meters, or aligned values.
- **State:** Cool colors mean healthy data, gold means attention, and red means failure.

### Inputs / Fields
- **Style:** Large black field with a gold outline and visible text cursor.
- **Focus:** The input overlays the existing frame rather than opening a generic window.

### Navigation
- **Style:** Keyboard-first command blocks embedded in the left spine.

### Protected Overlays
- **Shape:** A large rounded black well framed by a colored left rail and title bar.
- **State:** Ice for information and Mars for destructive confirmation.

## Do's and Don'ts

### Do:
- **Do** use large connected frame shapes to establish LCARS before adding small decoration.
- **Do** preserve black negative space between structural groups.
- **Do** keep telemetry labels aligned and values readable at a glance.
- **Do** render at the 1920x1080 design resolution before scaling.
- **Do** keep the terminal renderer as a recovery path.

### Don't:
- **Don't** imitate curves with character glyphs in graphical mode.
- **Don't** turn every status into a colored slab.
- **Don't** use red as normal structural decoration.
- **Don't** let ornamental reference codes compete with Kubernetes state.
- **Don't** claim Kmscon can host the graphical renderer concurrently.
- **Don't** make raw SDL KMSDRM or Cage Wayland the default launch path.
