export interface Track {
  id: number; type: string; selected?: boolean; external?: boolean;
  "external-filename"?: string; "ff-index"?: number; lang?: string; title?: string;
  codec?: string; "demux-channel-count"?: number; forced?: boolean;
}
export interface Artifact { path: string; sha256: string; revision: number; cue_count: number; complete_movie: boolean }
export interface Snapshot {
  instance_id: string; session_id: string; seek_epoch: number; snapshot_revision: number;
  profile_revision: number; state: string; stage: string; target: string;
  prepared_ranges: number[][]; installed_ranges: number[][]; buffer_wall_ms: number;
  language: {code: string; status: string}; artifact: Artifact | null;
  error: {code: string} | null; ready: boolean; duration_ms: number;
  stage_elapsed_s?: number; skipped_language_ranges?: number[][];
  failed_ranges?: number[][]; failure?: {code: string; detail?: string; range?: number[]} | null;
  metrics?: Record<string, unknown>;
}
export interface ChildGlobal {
  postMessage(name: string, data: unknown): void;
  onMessage(name: string, callback: (data: any) => void): void;
}
export interface ParentGlobal {
  postMessage(target: string, name: string, data: unknown): void;
  onMessage(name: string, callback: (data: any, sender: string) => void): void;
}
export type Connection = {host: string; port: number; token: string; protocol_version: number; instance_id: string};
