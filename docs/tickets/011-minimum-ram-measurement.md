# [TICKET-011] Measure memory on an 8 GB Mac and set the minimum RAM

## Status
`done`

## Dependencies
- Requires: #001 ✅

## Description
Cue's helper reached a peak memory footprint of 3.33 GB (kernel-reported, including Metal) and a maximum RSS of 2.0 GB. That was measured on a 36 GB M3 Max with a synthetic 18-second clip. IINA and video decoding also need memory. Whether an 8 GB Mac stays responsive during playback is unknown, and the answer decides the preflight threshold (#008) and the published requirement (#010).

## Acceptance Criteria
- [ ] On an 8 GB Apple Silicon Mac, a 20-minute playback with Cue translating is measured. The measurement covers helper peak footprint, memory pressure, swap, and whether playback stutters.
- [ ] The same measurement exists on a 16 GB Mac for comparison.
- [ ] The minimum RAM decision is recorded with the evidence. Either 8 GB is supported, supported with a warning, or refused.

## References
- `docs/feasibility.md` — prior performance and memory notes.
- `helper/src/cue/cli.py` — `benchmark` command.

## Implementation Notes
- Suggested approach: use `/usr/bin/time -l` for peak footprint, and `vm_stat`, `memory_pressure` and `sysctl vm.swapusage` sampled during playback.
- If no 8 GB Mac is available, record that, and default to requiring 16 GB until evidence exists.

## As-Built Notes

### 2026-09-25
- No 8 GB Apple Silicon Mac is available. The Macs on hand have 36 GB (M3 Max) and 64 GB (M1 Ultra). The 8 GB and 16 GB playback measurements were not run, so the first two acceptance criteria stay open.
- Decision, following the fallback in this ticket: Cue requires 16 GB. Macs with less memory are refused before any download. This is a default for lack of evidence, not a measured limit. `DEFAULT_RAM_BYTES` in `plugin/src/install-runtime.ts` is 16 GiB, and `docs/install-cue.md` says about 16 GB.
- Evidence so far: 3.33 GB peak footprint including Metal on the 36 GB M3 Max (18 s synthetic clip). On 2026-09-25, 2.11 GB peak RSS on the 64 GB M1 Ultra, from runtime 0.1.6 on a 54 s English clip translated to zh-TW; RSS excludes some Metal memory. Neither says whether an 8 GB Mac stays responsive during playback.
- Reopen this ticket when an 8 GB or 16 GB Apple Silicon Mac is available. Below 16 GB the sidebar shows "This Mac cannot run Cue" and hides its controls. To measure, use the developer install and turn on "Enable when a video lacks subtitles" in Cue's preferences, which starts Cue without the sidebar.

## Testing
- Record the raw numbers and the decision in `docs/feasibility.md`.
