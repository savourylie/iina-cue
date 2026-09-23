// IINA's manifest field is globalEntry. Process sharing is enforced by the
// helper's bootstrap lock and supervisor, rather than cross-context JS RPC.
// Player clients remain isolated; all inference goes through one worker.
export {};
