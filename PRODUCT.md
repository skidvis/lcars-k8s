# Product

<!-- impeccable:product-schema 1 -->

## Platform

terminal

## Users

Kubernetes operators using a dedicated Ubuntu Server virtual console or an SSH terminal. Their primary job is to assess cluster health, find problematic workloads, inspect details and logs, and take immediate pod actions without leaving the dashboard.

## Product Purpose

lcars-k8s is a keyboard-first Kubernetes operations dashboard with btop-like density and LCARS presentation. Success means live cluster state remains quickly scannable while common operational actions stay close at hand.

## Positioning

It combines practical Kubernetes telemetry and actions with a terminal-native LCARS visual language rather than applying a decorative theme to a conventional dashboard.

## Operating Context

The primary composition target is a pixel-rendered fullscreen SDL interface on a typical 1920x1080 Ubuntu Server display, hosted by a minimal Xorg kiosk started directly from the active kernel VT. The interface must retain a usable 80x24 Textual fallback for Kmscon, FbTerm, the kernel virtual console, and SSH.

## Capabilities and Constraints

The dashboard shows cluster CPU and memory history, per-node utilization, pods, nodes, events, logs, manifests, filtering, sorting, namespace scope, polling control, and confirmed pod deletion. Graphical mode uses pygame-ce and SDL to render antialiased geometry, bundled typography, and exact colors through a private Xorg server. Kmscon cannot own the same active display while graphical mode runs. Direct SDL KMSDRM is diagnostic-only because hardware and input support vary. Cage is not used because pygame-ce blocks while creating its Wayland display surface on the target system. The Textual fallback continues to support Kmscon, FbTerm, and the 16-color kernel console.

## Brand Commitments

The visual reference is Michael Okuda's LCARS system, with the linked GTJ LCARS site as a specific fidelity target. LCARS geometry and information framing must remain recognizable even in the restricted Linux console mode.

## Evidence on Hand

The repository contains runnable demo data, headless preview tooling, responsive stress helpers, a full-color preview, and a Linux-console preview.

## Product Principles

- Operational state is always more important than ornament.
- LCARS identity comes from composition and geometry, not decorative labels alone.
- Graphical mode owns visual fidelity; terminal mode owns universal recovery access.
- Keyboard workflows and Kubernetes behavior must remain stable across renderers.
- Compact layouts remove ornament before they remove essential data.
