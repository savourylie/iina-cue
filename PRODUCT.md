# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The surfaces are HTML pages rendered in WebViews inside IINA, a native macOS video player: the sidebar tab (`plugin/sidebar.html`) and the plugin preferences page (`plugin/preferences.html`). The user confirmed that the design language should stay close to macOS and IINA native conventions, so the pages should read as built-in IINA panels rather than a website.

## Users

- **Now:** the author, watching local videos in IINA on their own MacBook Pro (M3 Max).
- **Later:** general IINA users once Cue is published. UI decisions should already target them, not only the author.

The job: watch a local video with accurate subtitles in its original language or a chosen translation, without running separate tools beforehand or leaving the player.

## Product Purpose

Cue generates subtitles progressively while the video plays, using local models. It prepares captions near the playhead and attaches them to IINA as they become ready. Success means that captions show up quickly, stay in sync, and never take control of playback or subtitle selection away from the viewer.

## Positioning

Fully local, progressive AI subtitles inside IINA. The video, its audio and the captions stay on the Mac. There is no cloud service and no telemetry. Source timestamps come from forced alignment and are never invented.

## Operating Context

- The viewer is watching a video. The sidebar is a secondary, glanceable panel next to playback, often narrow.
- The work is asynchronous: caption coverage is prepared ahead of the playhead, has holes, and gets re-scoped after seeks. "Prepared" and "player-acknowledged" coverage are different states.
- Other entry points: the IINA Plugin menu (enable, stop, source language, retry, partial export) and the preferences page.
- For the development build, setup happens in the Terminal (`scripts/setup-dev`, `scripts/setup-models`). A Terminal-free installer is a v1 deliverable that does not exist yet.

## Capabilities and Constraints

- **Sidebar controls:** AI subtitles on/off, subtitle language (original, zh-TW, zh-CN, en, ja, ko), source language (auto-detect plus experimental languages), subtitle size, "Pause until captions are ready", and the translucent background box.
- **Advanced actions:** remux to MKV, export generated subtitles (incomplete exports are marked partial), and diagnostics.
- **Playback ownership:** Cue never resumes a pause the user made. Cue never reclaims a subtitle selection the user changed manually.
- **Language states:** "unknown language" is a valid state, not an error. Experimental source languages have not passed quality checks and must stay labelled as experimental.
- **Language of the UI:** English for now. Localization, including Traditional Chinese, is planned, so copy and layout should tolerate longer strings and keep strings extractable.
- **Scope of the product:** local, seekable media only. Streaming, external audio and a non-zero audio-delay are not supported.
- **Status of this build:** a technical preview (0.1.0) that has not passed v1 acceptance.

## Brand Commitments

- **Name:** Cue. The plugin title is "Cue for IINA · Technical Preview".
- **Tagline:** "Your videos. Your language. In sync."

## Evidence on Hand

- Feasibility and benchmark numbers are in `docs/feasibility.md` and `docs/acceptance.md`, measured on the author's M3 Max with synthetic speech.
- Quality on natural human speech has not been accepted. Do not claim speed advantages over other tools or broad language quality.

## Product Principles

1. **The viewer stays in control.** Playback, pauses and subtitle selection belong to the user. Cue suggests and prepares; it does not take over.
2. **Tell the truth about state.** Show real coverage, partial results, unknown language and experimental status honestly. Never imply that captions are ready when they are not.
3. **Stay out of the way.** The video is the focus. Cue should be glanceable and quiet unless something needs a decision.
4. **Local and private by construction.** Say plainly what runs locally and what is accessed.

## Accessibility & Inclusion

Support both light and dark appearance, respect reduced motion, and keep controls keyboard-reachable with visible focus, in line with macOS expectations. No stricter standard has been set.
