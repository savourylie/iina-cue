import type {Connection} from "./types";
declare const CUE_BOOTSTRAP_DEFAULT: string;
let connection: Connection | undefined;
let client: string | undefined;
let starting: Promise<void> | undefined;
let disposed = false;

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
    if (response.data.error && !response.data.session_id) throw new Error(response.data.error.code);
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
  if (disposed) throw new Error("DISPOSED");
  if (connection && client) return;
  if (starting) return starting;
  starting = (async () => {
    const bootstrap = iina.preferences.get("bootstrap") || CUE_BOOTSTRAP_DEFAULT;
    if (typeof bootstrap !== "string" || !bootstrap.startsWith("/") || !iina.file.exists(bootstrap)) throw new Error("SETUP_REQUIRED");
    const result = await iina.utils.exec(bootstrap,["ensure"]);
    if (result.status !== 0 || disposed) throw new Error("HELPER_DISCONNECTED");
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
  disposed = true;
  if (connection && client) void exchange("DELETE","/client").catch(()=>{}).finally(()=>{connection=undefined;client=undefined;});
}
