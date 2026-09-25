# [TICKET-013] General-user plugin build

## Status
`pending`

## Dependencies
- Requires: #009 ✅

## Description
`scripts/build-plugin.mjs` makes only the development pack. That pack is right for this Mac and wrong for anyone else:
- `CUE_BOOTSTRAP_DEFAULT` is set to this checkout's absolute `scripts/cue-helper` path. On another Mac, `planLaunch` in `plugin/src/launch.ts` checks that path, and a user who happens to have it would launch the wrong helper.
- `preferencesForPack(..., true)` makes the preferences page show the developer Terminal steps. `preferencesForPack(..., false)` exists, but nothing calls it.
- The output is always `dist/Cue.iinaplugin-0.1.0.iinaplgz`, and the build ends by printing "Built local development preview".

A general user needs a pack that starts only from the installed runtime (`~/Library/Application Support/Cue`), or else shows the sidebar setup. TICKET-012 installs this pack, and TICKET-014 publishes it.

## Acceptance Criteria
- [ ] One command builds a general-user `.iinaplgz`. Its bundled JavaScript contains no path from the build machine: no home folder, no checkout path, no `scripts/cue-helper`.
- [ ] With no installed runtime, the general-user pack shows the sidebar setup card. It never runs a helper from outside `~/Library/Application Support/Cue`. A non-empty `bootstrap` preference still works as an explicit override.
- [ ] The preferences page in the general-user pack hides the development block (`id="dev-setup"`).
- [ ] The general-user archive still passes `assertSafePluginArchive`: no Mach-O file, dylib or executable script.
- [ ] The file name carries the plugin version from `plugin/Info.json`, and the development and general-user packs cannot be confused by name.
- [ ] The development pack still builds and behaves as it does now. `npm run build` keeps working for development.

## References
- `scripts/build-plugin.mjs`: current single build path, esbuild `define`, IINA's `iina-plugin pack`.
- `scripts/preferences-pack.mjs`: `preferencesForPack(source, development)`.
- `scripts/check-plugin-archive.mjs`: archive safety check.
- `plugin/src/launch.ts`: `planLaunch`, installed mode versus the development bootstrap.
- `plugin/src/client.ts`: where `CUE_BOOTSTRAP_DEFAULT` is used.
- `plugin/Info.json`: version, name ("Technical Preview") and description ("Requires the Cue helper and models").

## Implementation Notes
- Required constraints: nothing inside the plugin package is executed (AGENTS.md, #005). Keep the user's existing specifications and README edits.
- Suggested approach: a build flag or a separate script, such as `npm run build:release`, that defines `CUE_BOOTSTRAP_DEFAULT` as an empty string and passes `development=false`. `planLaunch` already returns `SETUP_REQUIRED` when the development path is not absolute or does not exist.
- Decide whether the general-user pack keeps the "Technical Preview" name and the description "Requires the Cue helper and models". The sidebar now installs both.

## Testing
- Unit tests: the general-user bundle has no build-machine path, the preferences development block is hidden, and `planLaunch` with an empty development path and no installed marker returns `SETUP_REQUIRED`.
- `scripts/test` and `npm run build` pass. The new release build command passes and prints the archive path.
- Manual: unpack the general-user `.iinaplgz` and `grep` it for `/Users/`.
