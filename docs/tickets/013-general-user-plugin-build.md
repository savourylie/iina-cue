# [TICKET-013] General-user plugin build

## Status
`done`

## Dependencies
- Requires: #009 ✅

## Description
`scripts/build-plugin.mjs` makes only the development pack. That pack is right for this Mac and wrong for anyone else:
- `CUE_BOOTSTRAP_DEFAULT` is set to this checkout's absolute `scripts/cue-helper` path. On another Mac, `planLaunch` in `plugin/src/launch.ts` checks that path, and a user who happens to have it would launch the wrong helper.
- `preferencesForPack(..., true)` makes the preferences page show the developer Terminal steps. `preferencesForPack(..., false)` exists, but nothing calls it.
- The output is always `dist/Cue.iinaplugin-0.1.0.iinaplgz`, and the build ends by printing "Built local development preview".

A general user needs a pack that starts only from the installed runtime (`~/Library/Application Support/Cue`), or else shows the sidebar setup. TICKET-012 installs this pack, and TICKET-014 publishes it.

## Acceptance Criteria
- [x] One command builds a general-user `.iinaplgz`. Its bundled JavaScript contains no path from the build machine: no home folder, no checkout path, no `scripts/cue-helper`.
- [x] With no installed runtime, the general-user pack shows the sidebar setup card. It never runs a helper from outside `~/Library/Application Support/Cue`. A non-empty `bootstrap` preference still works as an explicit override.
- [x] The preferences page in the general-user pack hides the development block (`id="dev-setup"`).
- [x] The general-user archive still passes `assertSafePluginArchive`: no Mach-O file, dylib or executable script.
- [x] The file name carries the plugin version from `plugin/Info.json`, and the development and general-user packs cannot be confused by name.
- [x] The development pack still builds and behaves as it does now. `npm run build` keeps working for development.

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

## As-Built Notes

### 2026-09-25
- `npm run build:release` (`node scripts/build-plugin.mjs --release`) makes `dist/Cue-<version>.iinaplgz`. `npm run build` still makes the development pack, now named `dist/Cue-<version>-dev.iinaplgz` instead of `Cue.iinaplugin-0.1.0.iinaplgz`, so the two cannot be mixed up. The version comes from `plugin/Info.json`.
- The release build defines `CUE_BOOTSTRAP_DEFAULT` as an empty string, and packs `preferences.html` with the development block hidden. `planLaunch` then either uses the installed runtime, uses an explicit `bootstrap` preference, or reports `SETUP_REQUIRED`. The build stops if either bundle contains the checkout path, the home folder, `/Users/` or `scripts/cue-helper`.
- The release bundle is written to `dist/release/`. Only the development build writes `plugin/dist/`, because the development link loads that folder. Sharing one output folder would break the linked development plugin after every release build.
- `plugin/Info.json` is unchanged. Whether the general-user pack keeps "Technical Preview" in its name and "Requires the Cue helper and models" in its description is left for the user; the sidebar now installs both.
- Not run in IINA. Installing the general-user pack here would replace the development link, which shares the identifier `io.iina.cue`. The first IINA run of this pack is TICKET-012 on a clean Mac.

## Testing
- Unit tests: the general-user bundle has no build-machine path, the preferences development block is hidden, and `planLaunch` with an empty development path and no installed marker returns `SETUP_REQUIRED`.
- `scripts/test` and `npm run build` pass. The new release build command passes and prints the archive path.
- Manual: unpack the general-user `.iinaplgz` and `grep` it for `/Users/`.
