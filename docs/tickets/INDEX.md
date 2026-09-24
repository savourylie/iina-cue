# Ticket Index

> **Last updated**: 2026-09-25

Goal: anyone can install Cue without Terminal, and nothing triggers a macOS malware warning. The source is the 2026-09-24 feasibility and notarization work in this project.

## Summary

| Status | Count |
| --- | --- |
| ✅ Done | 6 |
| 🔧 In Progress | 0 |
| 📋 Pending | 2 |
| 🚫 Blocked | 4 |
| ⏸️ Deferred | 0 |

## Runtime and release

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 001 | [Build a relocatable helper runtime](./001-build-relocatable-helper-runtime.md) | `done` | — | Built: 1.0G, or 256M as tar.xz |
| 002 | [Build a static LGPL FFmpeg](./002-static-lgpl-ffmpeg.md) | `done` | — | FFmpeg 7.1.1 built in 28 s; media tests pass |
| 003 | [License notices and THIRD_PARTY_NOTICES](./003-license-notices.md) | `done` | #001 ✅, #002 ✅ | licenses/ ships with the runtime |
| 004 | [Sign and notarize the runtime](./004-sign-and-notarize-runtime.md) | `done` | #001 ✅, #002 ✅, #003 ✅ | Notarized; minimum macOS 27.0 |
| 007 | [Hosting and release manifest](./007-host-release-artifacts.md) | `pending` | #004 ✅ | Needs the user's publishing decision |

## Helper and plugin

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 005 | [Helper runs from an installed runtime](./005-helper-runs-from-installed-runtime.md) | `done` | — | Bundled FFmpeg only; nothing executed from the plugin package |
| 006 | [Setup API: model download and smoke test](./006-helper-setup-api-model-download.md) | `done` | #005 ✅ | Resumable, verified, consent-first |
| 008 | [Plugin installs and updates the runtime](./008-plugin-installs-runtime.md) | `blocked` | #005 ✅, #007 | Downloads with curl or http.download, which leave no quarantine flag |
| 009 | [Sidebar "Set up Cue" flow](./009-sidebar-set-up-cue-flow.md) | `blocked` | #006, #008 | Follows DESIGN.md; includes credits |

## Docs and verification

| # | Ticket | Status | Depends On | Notes |
| --- | --- | --- | --- | --- |
| 010 | [End-user install guide](./010-end-user-install-guide.md) | `blocked` | #009 | Explains IINA's permission warning |
| 011 | [Minimum RAM on an 8 GB Mac](./011-minimum-ram-measurement.md) | `pending` | #001 ✅ | Needs an 8 GB Mac; defaults to 16 GB |
| 012 | [**TEST: Checkpoint 1 — Clean install on a SIP-enabled Mac**](./012-test-checkpoint-1-clean-mac-install.md) | `blocked` | #004 ✅, #008, #009, #010, #011 | Gate: public release for general users |

## Status Key

| Status | Meaning |
| --- | --- |
| `pending` | Ready to start; all dependencies met |
| `in-progress` | Currently being implemented |
| `done` | Implemented and verified |
| `blocked` | Waiting on a dependency |
| `deferred` | Intentionally postponed; reason noted |
