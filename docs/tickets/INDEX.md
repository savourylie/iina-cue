# Ticket Index

> **Last updated**: 2026-09-25

Goal: anyone can install Cue without Terminal, and nothing triggers a macOS malware warning. The source is the 2026-09-24 feasibility and notarization work in this project.

## Summary

| Status | Count |
| --- | --- |
| ✅ Done | 11 |
| 🔧 In Progress | 0 |
| 📋 Pending | 5 |
| 🚫 Blocked | 2 |
| ⏸️ Deferred | 0 |

## Runtime and release

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 001 | [Build a relocatable helper runtime](./001-build-relocatable-helper-runtime.md) | `done` | — | Built: 1.0G, or 256M as tar.xz |
| 002 | [Build a static LGPL FFmpeg](./002-static-lgpl-ffmpeg.md) | `done` | — | FFmpeg 7.1.1 built in 28 s; media tests pass |
| 003 | [License notices and THIRD_PARTY_NOTICES](./003-license-notices.md) | `done` | #001 ✅, #002 ✅ | licenses/ ships with the runtime |
| 004 | [Sign and notarize the runtime](./004-sign-and-notarize-runtime.md) | `done` | #001 ✅, #002 ✅, #003 ✅ | Notarized. Runtime 0.1.6 was re-notarized for macOS 14.0 (see #007) |
| 007 | [Hosting and release manifest](./007-host-release-artifacts.md) | `done` | #004 ✅ | Runtime 0.1.6 on Hugging Face, GitHub Release as backup; minimum macOS 14.0 |
| 014 | [Publish the plugin release](./014-publish-plugin-release.md) | `blocked` | #013 | Confirm how IINA's Install from GitHub finds a plugin first; user approves the publish |

## Helper and plugin

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 005 | [Helper runs from an installed runtime](./005-helper-runs-from-installed-runtime.md) | `done` | — | Bundled FFmpeg only; nothing executed from the plugin package |
| 006 | [Setup API: model download and smoke test](./006-helper-setup-api-model-download.md) | `done` | #005 ✅ | Resumable, verified, consent-first |
| 008 | [Plugin installs and updates the runtime](./008-plugin-installs-runtime.md) | `done` | #005 ✅, #007 ✅ | Downloads with curl or http.download, which leave no quarantine flag |
| 009 | [Sidebar "Set up Cue" flow](./009-sidebar-set-up-cue-flow.md) | `done` | #006 ✅, #008 ✅ | Follows DESIGN.md; includes credits |
| 013 | [General-user plugin build](./013-general-user-plugin-build.md) | `pending` | #009 ✅ | No build-machine path in the bundle; Terminal steps hidden |
| 015 | [Detect stretches without speech with Silero VAD](./015-silero-vad-no-speech.md) | `pending` | #001 ✅, #004 ✅, #007 ✅ | Music or quiet openings: no "Language unclear", no session error; runtime 0.1.7 |
| 016 | [Plugin replaces an outdated runtime](./016-plugin-updates-outdated-runtime.md) | `pending` | #008 ✅ | #008's newer-runtime swap was never implemented |
| 017 | [One failed window never stops captions](./017-captions-survive-failed-windows.md) | `pending` | — | Constrained translation JSON, no kana in Chinese, failed windows become holes |
| 018 | [Optional larger models in Advanced](./018-optional-larger-models.md) | `pending` | #006 ✅, #009 ✅ | Gemma 4 E4B (3.66 GB) and 12B (6.88 GB); E2B stays default |

## Docs and verification

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 010 | [End-user install guide](./010-end-user-install-guide.md) | `done` | #009 ✅ | Explains IINA's permission warning |
| 011 | [Minimum RAM on an 8 GB Mac](./011-minimum-ram-measurement.md) | `done` | #001 ✅ | No 8 GB Mac available; 16 GB required by default, not measured |
| 012 | [**TEST: Checkpoint 1 — Clean install on a SIP-enabled Mac**](./012-test-checkpoint-1-clean-mac-install.md) | `blocked` | #004 ✅, #008 ✅, #009 ✅, #010 ✅, #011 ✅, #013, #014 | Gate: public release for general users. See the prerequisites below |

## Before TICKET-012 can run

012 is the first run inside IINA, on a Mac that has never been used for development. It waits on these:

| # | Prerequisite | State | What is missing |
| --- | --- | --- | --- |
| 1 | #011: minimum RAM decided | ✅ done | 16 GB by default. No 8 GB Mac was available to measure |
| 2 | #013: general-user plugin build | 📋 pending, ready to start | `scripts/build-plugin.mjs` builds only the development pack, with this checkout's helper path and the Terminal steps |
| 3 | #014: published plugin release | 🚫 blocked on #013 | Both install routes in 012 need a general-user `.iinaplgz` on a GitHub Release. Publishing needs the user's approval at the time |
| 4 | The test Mac | ⏳ user | Apple Silicon, SIP on, IINA 1.4 or later, 16 GB or more (#011). No Homebrew, Python, Node or project checkout. macOS 14–26 is preferred, because every run so far was on macOS 27.2 and 14.0 is the new minimum |

Already in place: runtime 0.1.6 (macOS 14.0, notarized) on Hugging Face with a GitHub backup, the sidebar setup flow, the real model download and smoke test (#006), and the install guide (#010).

## Status Key

| Status | Meaning |
| --- | --- |
| `pending` | Ready to start; all dependencies met |
| `in-progress` | Currently being implemented |
| `done` | Implemented and verified |
| `blocked` | Waiting on a dependency |
| `deferred` | Intentionally postponed; reason noted |
