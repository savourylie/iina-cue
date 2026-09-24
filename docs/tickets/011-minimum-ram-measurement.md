# [TICKET-011] Measure memory on an 8 GB Mac and set the minimum RAM

## Status
`pending`

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

## Testing
- Record the raw numbers and the decision in `docs/feasibility.md`.
