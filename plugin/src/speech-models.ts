import {formatBytes} from "./setup-view";
import {t, type StringKey} from "./strings";

/** One speech model as the helper reports it in GET /setup. */
export interface ModelStatus {
  /** bytes is the download; disk_bytes adds the compile cache LiteRT-LM writes on first use. */
  id: string; bytes: number; disk_bytes: number; bytes_done: number; state: "installed" | "partial" | "missing";
  optional: boolean; min_ram_bytes: number; fits_memory: boolean; selected: boolean;
}
export interface ModelsStatus {
  selected: string; ram_bytes: number; models: ModelStatus[];
  download: {model: string; phase: string; error?: {code: string; detail?: string} | null} | null;
  trial: {model: string; phase: string; reason?: string | null; seconds?: number | null} | null;
}
export type ModelAction = "download" | "cancel" | "use" | "remove";
/** What the sidebar draws for one model. All text is already localized. */
export interface ModelRow {
  id: string; name: string; description: string; facts: string;
  checked: boolean; disabled: boolean; note: string; noteTone: "" | "error";
  progress: number | null; bytes: string; actions: {action: ModelAction; label: string}[];
}

const gb = (bytes: number) => Math.round(bytes / 2 ** 30);

/** A helper error from the last model action, shown under that model. */
export function modelErrorText(code: string, model: ModelStatus | undefined): string {
  if (code === "SETUP_BUSY") return t("model.busy");
  if (code === "LOW_MEMORY" && model) return t("model.lowMemory", {needed: gb(model.min_ram_bytes)});
  if (code === "DISK_FULL" && model) return t("model.diskFull", {size: formatBytes(model.disk_bytes - model.bytes_done)});
  return t("model.failed");
}

export function modelRows(status: ModelsStatus | null, lastError: {model: string; code: string} | null = null): ModelRow[] {
  if (!status) return [];
  const download = status.download, trial = status.trial;
  const working = download?.phase === "downloading" || trial?.phase === "smoking";
  return status.models.map((model) => {
    const downloading = download?.model === model.id && download.phase === "downloading";
    const trying = trial?.model === model.id && trial.phase === "smoking";
    const installed = model.state === "installed";
    const actions: ModelRow["actions"] = [];
    let note = "", noteTone: ModelRow["noteTone"] = "";
    if (downloading) {
      actions.push({action: "cancel", label: t("model.cancel")});
      note = t("model.downloading");
    } else if (trying) {
      note = t("model.trying");
    } else if (!model.fits_memory && !model.selected) {
      note = t("model.lowMemory", {needed: gb(model.min_ram_bytes)});
    } else if (!installed && model.optional && !working) {
      actions.push({action: "download", label: t(model.state === "partial" ? "model.resume" : "model.download", {size: formatBytes(model.bytes)})});
    } else if (installed && !model.selected && model.optional && !working) {
      actions.push({action: "remove", label: t("model.remove")});
    }
    if (model.selected) note = trial?.model === model.id && trial.phase === "passed" && trial.seconds != null
      ? t("model.inUseTested", {seconds: trial.seconds}) : t("model.inUse");
    if (trial?.model === model.id && (trial.phase === "failed" || trial.phase === "interrupted")) {
      note = t("model.trialFailed"); noteTone = "error";
    }
    if (download?.model === model.id && download.phase === "error") { note = t("model.downloadStopped"); noteTone = "error"; }
    if (lastError?.model === model.id) { note = modelErrorText(lastError.code, model); noteTone = "error"; }
    const key = (part: string) => `model.${model.id}.${part}` as StringKey;
    return {
      id: model.id,
      name: t(key("name")),
      description: t(key("description")),
      facts: !model.optional ? t("model.factsDefault", {memory: gb(model.min_ram_bytes)})
        : installed ? t("model.factsInstalled", {disk: formatBytes(model.disk_bytes), memory: gb(model.min_ram_bytes)})
        : t("model.facts", {size: formatBytes(model.bytes), disk: formatBytes(model.disk_bytes), memory: gb(model.min_ram_bytes)}),
      checked: model.selected,
      // Only a complete, verified model that fits this Mac can be chosen, and not mid-task.
      disabled: !installed || !model.fits_memory || working,
      note, noteTone,
      progress: downloading && model.bytes > 0 ? Math.floor((100 * model.bytes_done) / model.bytes) : null,
      bytes: downloading ? t("sidebar.setupBytes", {done: formatBytes(model.bytes_done), total: formatBytes(model.bytes),
        percent: Math.floor((100 * model.bytes_done) / Math.max(1, model.bytes))}) : "",
      actions,
    };
  });
}

/** Keep polling while the helper is downloading or trying a model. */
export function modelsBusy(status: ModelsStatus | null): boolean {
  return status?.download?.phase === "downloading" || status?.trial?.phase === "smoking";
}
