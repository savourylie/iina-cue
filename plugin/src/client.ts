import type {Connection} from "./types";
import {planLaunch} from "./launch";
declare const CUE_BOOTSTRAP_DEFAULT: string;
let connection: Connection | undefined;
let client: string | undefined;
let starting: Promise<void> | undefined;

function resolvePath(path: string): string | null {
  // Call this on iina.utils. A detached Objective-C method throws
  // "self type check failed" inside IINA.
  const utils = iina.utils as {resolvePath?: (path: string) => string | null | undefined};
  if (typeof utils.resolvePath !== "function") return null;
  const resolved = utils.resolvePath(path);
  return typeof resolved === "string" && resolved.startsWith("/") ? resolved : null;
}

async function exchange(method: string, path: string, data: unknown = {}): Promise<any> {
  const c = connection;
  if (!c) throw new Error("HELPER_DISCONNECTED");
  const api = iina.http[method.toLowerCase() as "get" | "post" | "put" | "delete"].bind(iina.http);
  try {
    const response = await api(`http://127.0.0.1:${c.port}/v1${path}`, {params:{}, headers:{
      Authorization:`Bearer ${c.token}`, ...(client ? {"X-Cue-Client":client} : {})
    }, data:method === "GET" ? {} : {payload:JSON.stringify(data)}});
    if (response.data.instance_id !== c.instance_id) throw new Error("HELPER_DISCONNECTED");
    // A successful session snapshot may contain a background inference error
    // alongside usable installed coverage. It is not a transport failure.
    if (response.data.error && !response.data.session_id && !response.data.job_id) throw new Error(response.data.error.code);
    return response.data;
  } catch (error: any) {
    const code = error?.data?.error?.code || error?.message || "HELPER_DISCONNECTED";
    if (["CLIENT_REQUIRED","HELPER_DISCONNECTED"].includes(code) || (!error?.data?.error && !["STALE_ACK","STALE_EPOCH","STALE_SEQUENCE"].includes(code))) {
      connection = undefined; client = undefined;
    }
    throw new Error(code);
  }
}

async function ensure(): Promise<void> {
  if (connection && client) return;
  if (starting) return starting;
  starting = (async () => {
    const preference = iina.preferences.get("bootstrap");
    const plan = planLaunch({
      preference,
      devBootstrap: CUE_BOOTSTRAP_DEFAULT,
      exists: (path) => iina.file.exists(path),
      resolve: resolvePath,
    });
    const result = await iina.utils.exec(plan.file, plan.args);
    if (result.status !== 0) {
      let code = "HELPER_DISCONNECTED";
      try { code = JSON.parse(result.stderr).error.code || code; } catch {}
      throw new Error(code);
    }
    const c = JSON.parse(result.stdout) as Connection;
    if (c.protocol_version !== 1 || c.host !== "127.0.0.1" || !Number.isInteger(c.port) || c.port<1 || c.port>65535 || !/^[a-f0-9]{64}$/.test(c.token)) throw new Error("PROTOCOL_MISMATCH");
    connection = c;
    client = (await exchange("POST","/clients")).client_id;
  })();
  try {await starting;} finally {starting = undefined;}
}

/** Each player owns a client lease; the flocked supervisor owns the one worker.
 * Avoid relaying mutable asynchronous replies through a second JS context.
 * Nothing in the webview receives connection credentials.
 */
export async function rpc<T = any>(method: string, path: string, body: unknown = {}): Promise<T> {
  await ensure();
  return exchange(method,path,body);
}
export function disposeClient(): void {
  // Best-effort lease release that never bricks the plugin: the next rpc()
  // reconnects on demand, so closing and reopening player windows just works.
  // Server-side client/session leases remain the crash fallback.
  if (!connection) return;
  const drop = exchange("DELETE", "/client").catch(() => {});
  connection = undefined; client = undefined;
  void drop;
}
