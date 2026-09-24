---
name: Cue for IINA
description: Local, progressive AI subtitles in a quiet native IINA sidebar.
colors:
  accent-fallback: "#3d55d9"
  accent-fallback-dark: "#6f82ff"
  focus-fallback: "#3d55d9"
  focus-fallback-dark: "#8f9dff"
  tone-working: "#5468e0"
  tone-working-dark: "#8797ff"
  tone-ready: "#1d7f47"
  tone-ready-dark: "#4fcf82"
  tone-info: "#6e6e73"
  tone-info-dark: "#a1a1a6"
  tone-warning: "#a8570a"
  tone-warning-dark: "#ffb04a"
  tone-error: "#c0283d"
  tone-error-dark: "#ff7585"
  text-ready: "#17663a"
  text-ready-dark: "#7fd9a3"
  text-error: "#a3202f"
  text-error-dark: "#ff8190"
  separator: "rgb(0 0 0 / .14)"
  separator-dark: "rgb(255 255 255 / .16)"
  fill: "rgb(0 0 0 / .05)"
  fill-dark: "rgb(255 255 255 / .06)"
  fill-hover: "rgb(0 0 0 / .08)"
  fill-hover-dark: "rgb(255 255 255 / .1)"
  switch-off: "rgb(0 0 0 / .42)"
  switch-off-dark: "rgb(255 255 255 / .34)"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.45
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  hint:
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.02em"
rounded:
  row: "5px"
  panel: "7px"
  track: "3px"
  pill: "999px"
spacing:
  gutter: "16px"
  field: "12px"
  section: "18px"
components:
  status-row:
    backgroundColor: "{colors.fill}"
    rounded: "{rounded.panel}"
    padding: "8px 10px"
  action-row:
    rounded: "{rounded.row}"
    padding: "6px 8px"
  action-row-hover:
    backgroundColor: "{colors.fill-hover}"
  inline-form:
    backgroundColor: "{colors.fill}"
    rounded: "{rounded.panel}"
    padding: "10px"
  switch-track:
    backgroundColor: "{colors.switch-off}"
    rounded: "{rounded.pill}"
    width: "32px"
    height: "18px"
  coverage-track:
    rounded: "{rounded.track}"
    height: "6px"
---

# Design System: Cue for IINA

## Overview

**Creative North Star: "The Quiet Inspector"**

Cue lives in an IINA sidebar tab next to a video someone is watching. It should read like one of IINA's own inspector panels: system type, native controls, hairline section breaks, and nothing that competes with the film. The panel is quiet by default. Only the status row speaks, and it speaks in the viewer's language: what is happening, what they can do next, and nothing it cannot prove.

The system is restrained on purpose. Native macOS controls (popup menus, checkboxes, sliders, push buttons, text fields) carry most of the interface, tinted by the user's own system accent. Custom styling is spent only where Cue has something no native control can say: the status row and the coverage strip.

Density follows macOS inspectors: 13px text, tight field groups, generous gaps between sections, and help text that appears only when it applies.

**Key Characteristics:**
- Transparent page over IINA's sidebar material; colors come from system colors and light/dark tokens.
- One status row, directly under the AI subtitles switch, carries every state, error and recovery.
- Native controls first; the user's AccentColor, not a Cue brand color.
- Help is contextual: shown next to the control it explains, only when it applies.
- Works at 240px and in both appearances without horizontal scrolling.

## Colors

The palette is system-derived: text is CanvasText, accents are the user's AccentColor, and Cue's own colors exist only to signal status.

### Primary
- **System Accent** (AccentColor): switch on-state, slider, checkboxes and progress. The fallbacks (`accent-fallback`, `accent-fallback-dark`) apply only where AccentColor is unsupported.

### Tertiary
- **Working Periwinkle** (`tone-working`): preparation in progress; the status dot pulses.
- **Ready Green** (`tone-ready`): captions loaded in the player at the playhead.
- **Caution Amber** (`tone-warning`): partial failure, unclear language, or a failed action while captions still work.
- **Stop Red** (`tone-error`): Cue has stopped preparing captions.
- **Quiet Grey** (`tone-info`): neutral outcomes such as an export or a kept subtitle selection.
- **Readable Green / Readable Red** (`text-ready`, `text-error`): the only tone colors used as text, tuned to at least 4.5:1 on light and dark sidebars.

### Neutral
- **CanvasText**: all body text. Secondary text is CanvasText at reduced opacity (0.75–0.8 for hints, 0.62–0.65 for labels and scales), never a separate grey.
- **Hairline** (`separator`): section dividers.
- **Wash** (`fill`, `fill-hover`): the inline form background and hover rows.

### Named Rules
**The Tone Carries Meaning, Words Carry It Too Rule.** Every tone is paired with a headline that states the same thing in words. Color is never the only signal.

**The Tint, Not Paint Rule.** A tone appears as the status dot, a 9% tint of the status row, and the coverage fill. Large solid areas of tone color are not used.

## Typography

**Body Font:** the system font (-apple-system, with BlinkMacSystemFont and sans-serif fallbacks)

**Character:** One family at macOS inspector sizes. Hierarchy comes from weight and opacity, not from size jumps.

### Hierarchy
- **Title** (600, 13px): the switch label, status headline, disclosure summaries, and form labels that start a group.
- **Body** (400, 13px, 1.45): control labels and option text.
- **Hint** (400, 12px, 1.4, 0.75–0.8 opacity): field hints, status detail, form notes.
- **Label** (600, 11px, 0.02em tracking, 0.62 opacity): section headings (Language, Appearance, Playback) and the coverage scale.
- The preferences window steps up to a 17px/600 page title over 13px body text.

### Named Rules
**The Tabular Numbers Rule.** Changing numbers (subtitle size, progress percent, coverage scale, error codes) use tabular numerals so they do not jitter.

## Layout

A single column with a 16px side gutter. The first section holds the switch and the status row. Language, Appearance and Playback follow, each opened by a small label heading and separated by a hairline with 18px above and 14px below. Fields inside a section sit 12px apart. Advanced closes the page as a disclosure.

The layout is fluid from 240px upward. Long paths and filenames wrap inside their own lines. Action buttons in the status row always sit below the text, so the text keeps the full width.

## Elevation & Depth

Flat. The sidebar sits on IINA's own material, so Cue adds no shadows except the tiny thumb shadow on the switch (`0 1px 2px` at 30% black). Grouping comes from hairlines and tinted washes.

### Named Rules
**The No-Card Rule.** Content is never boxed into cards. The only filled containers are the status row and the inline MKV form, both because they are temporary, stateful surfaces.

## Shapes

Gently rounded: 7px for the status row and inline form, 5px for hover rows, 3px for the coverage track, and a full pill for the switch. Native controls keep their system shapes.

## Components

### Status Row
The panel's one voice.
- **Structure:** an 8px tone dot, a 13px/600 headline, a 12px detail, an optional small "Error code: …" line, an optional action button (Retry or Show in Finder) below the text, and an optional coverage strip.
- **Tone:** set by `data-tone` (off, working, ready, info, warning, error). The row background is the tone mixed at 9% into transparent. Off hides the row.
- **Accessibility:** a separate off-screen polite announcer speaks the headline, plus the detail for warnings and errors. The row itself is not live, so ticking seconds are not re-read.
- **Motion:** the working dot pulses (1.6s); reduced motion shows it static at 0.7 opacity.

### Coverage Strip
Shows where captions exist, not just how far ahead.
- A 6px track covering the next 90 seconds after the playhead, labeled "Now" and "+90 s".
- Solid tone for ranges loaded in the player; the same tone at 35% for ranges prepared but not yet loaded; empty track for holes.
- Its accessible name is a one-sentence summary of the same facts.

### Switch
- The only custom control, because the master AI subtitles toggle sits on one row with its label: a 32×18 pill track and a 14px white thumb that slides 14px. It fills with AccentColor when on.
- Focus draws the native focus ring around the track.

### Buttons
- **Native push buttons** for Retry, Show in Finder, Save copy and Cancel. In forms, Cancel comes before the primary action, matching macOS.
- **Action rows** in Advanced: full-width, left-aligned text buttons, transparent at rest with the hover wash.

### Inputs / Fields
- Native popup menus, checkboxes, slider and text field, tinted by AccentColor.
- **Hints** sit directly under the field they describe and appear only when they apply.
- **Error:** the message appears under the field in readable red, the field gets a 1px red outline and `aria-invalid`, and the submit button is disabled until the problem is fixed.

### Disclosures
- Advanced and Developer diagnostics are plain disclosure triangles (a small rotated chevron), never boxed buttons. Developer tools stay nested inside Advanced.

## Do's and Don'ts

### Do:
- **Do** put every Cue state, error and recovery in the status row under the switch.
- **Do** use native controls and AccentColor; add custom styling only for what native controls cannot express.
- **Do** keep secondary text as CanvasText at 0.75–0.8 opacity, and check that it stays at 4.5:1 or more on light and dark sidebars.
- **Do** show help next to the control it explains, and only when it applies.
- **Do** test every change at 240px and 360px in light and dark, and finally in IINA's WKWebView.

### Don't:
- **Don't** put an error code or internal term in a headline. Codes go on the small "Error code" line.
- **Don't** add cards, shadows, gradients or a brand color to the sidebar.
- **Don't** make a live region out of anything that changes on every poll.
- **Don't** use the error tone for states where captions still work; use the warning tone.
- **Don't** add always-on explanatory paragraphs to the sidebar.
