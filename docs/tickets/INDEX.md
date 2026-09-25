# Ticket Index

> **Last updated**: 2026-09-25

Goal: anyone can install Cue without Terminal, and nothing triggers a macOS malware warning. The source is the 2026-09-24 feasibility and notarization work in this project.

## Summary

| Status | Count |
| --- | --- |
| ✅ Done | 10 |
| 🔧 In Progress | 0 |
| 📋 Pending | 1 |
| 🚫 Blocked | 1 |
| ⏸️ Deferred | 0 |

## Runtime and release

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 001 | [Build a relocatable helper runtime](./001-build-relocatable-helper-runtime.md) | `done` | — | Built: 1.0G, or 256M as tar.xz |
| 002 | [Build a static LGPL FFmpeg](./002-static-lgpl-ffmpeg.md) | `done` | — | FFmpeg 7.1.1 built in 28 s; media tests pass |
| 003 | [License notices and THIRD_PARTY_NOTICES](./003-license-notices.md) | `done` | #001 ✅, #002 ✅ | licenses/ ships with the runtime |
| 004 | [Sign and notarize the runtime](./004-sign-and-notarize-runtime.md) | `done` | #001 ✅, #002 ✅, #003 ✅ | Notarized. Runtime 0.1.6 was re-notarized for macOS 14.0 (see #007) |
| 007 | [Hosting and release manifest](./007-host-release-artifacts.md) | `done` | #004 ✅ | Runtime 0.1.6 on Hugging Face, GitHub Release as backup; minimum macOS 14.0 |

## Helper and plugin

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 005 | [Helper runs from an installed runtime](./005-helper-runs-from-installed-runtime.md) | `done` | — | Bundled FFmpeg only; nothing executed from the plugin package |
| 006 | [Setup API: model download and smoke test](./006-helper-setup-api-model-download.md) | `done` | #005 ✅ | Resumable, verified, consent-first |
| 008 | [Plugin installs and updates the runtime](./008-plugin-installs-runtime.md) | `done` | #005 ✅, #007 ✅ | Downloads with curl or http.download, which leave no quarantine flag |
| 009 | [Sidebar "Set up Cue" flow](./009-sidebar-set-up-cue-flow.md) | `done` | #006 ✅, #008 ✅ | Follows DESIGN.md; includes credits |

## Docs and verification

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 010 | [End-user install guide](./010-end-user-install-guide.md) | `done` | #009 ✅ | Explains IINA's permission warning |
| 011 | [Minimum RAM on an 8 GB Mac](./011-minimum-ram-measurement.md) | `pending` | #001 ✅ | Needs an 8 GB Mac. Without one, record that and keep 16 GB; that also closes it |
| 012 | [**TEST: Checkpoint 1 — Clean install on a SIP-enabled Mac**](./012-test-checkpoint-1-clean-mac-install.md) | `blocked` | #004 ✅, #008 ✅, #009 ✅, #010 ✅, #011 | Gate: public release for general users. Also needs the three prerequisites below |

## Before TICKET-012 can run

012 is the first run inside IINA, on a Mac that has never been used for development. It waits on these:

| # | Prerequisite | State | What is missing |
| --- | --- | --- | --- |
| 1 | #011: minimum RAM decided | ⏳ pending | An 8 GB Mac measurement. Without one, record that and keep the 16 GB requirement |
| 2 | A general-user plugin build | ❌ no ticket yet | `scripts/build-plugin.mjs` builds only the development pack. That pack bakes in this checkout's helper path and shows the Terminal steps. `preferencesForPack(..., false)` exists but nothing calls it |
| 3 | A published plugin release | ❌ no ticket yet | 012 tests both a browser-downloaded `.iinaplgz` and IINA's "Install from GitHub". Neither has a published general-user plugin to install yet |
| 4 | The test Mac | ⏳ user | Apple Silicon, SIP on, IINA 1.4 or later, 16 GB or more (until #011 says otherwise). No Homebrew, Python, Node or project checkout. macOS 14–26 is preferred, because every run so far was on macOS 27.2 and 14.0 is the new minimum |

Already in place: runtime 0.1.6 (macOS 14.0, notarized) on Hugging Face with a GitHub backup, the sidebar setup flow, the real model download and smoke test (#006), and the install guide (#010).

## Status Key

| Status | Meaning |
| --- | --- |
| `pending` | Ready to start; all dependencies met |
| `in-progress` | Currently being implemented |
| `done` | Implemented and verified |
| `blocked` | Waiting on a dependency |
| `deferred` | Intentionally postponed; reason noted |
