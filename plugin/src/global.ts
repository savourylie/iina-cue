// IINA's manifest field is globalEntry. Process sharing is enforced by the
// helper's bootstrap lock and supervisor, rather than cross-context JS RPC.
// Player clients remain isolated; all inference goes through one worker.
//
// One relay lives here: a helper update has to turn captions off in every IINA
// window before the old helper can stop, and back on afterwards. A window can
// only message this global instance, and IINA's broadcast reaches only windows a
// plugin opened itself, so each window says hello and is addressed by its label.
import type {ParentGlobal} from "./types";

export function relayRuntimeUpdates(global: ParentGlobal): void {
  const players = new Set<string>();
  const remember = (sender: unknown) => { if (typeof sender === "string" && sender) players.add(sender); };
  global.onMessage("cue-hello", (_data, sender) => remember(sender));
  global.onMessage("cue-update", (data, sender) => {
    remember(sender);
    // A closed window's label no longer matches a player; IINA ignores it.
    for (const label of players) global.postMessage(label, "cue-update", data);
  });
}

const host = globalThis as {iina?: {global?: ParentGlobal}};
if (host.iina?.global) relayRuntimeUpdates(host.iina.global);
