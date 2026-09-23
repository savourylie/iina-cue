type MpvOptionAccess = {getString(name: string): string; set(name: string, value: string): void};

// mpv's colors use #AARRGGBB: 0x99 is a 60% opaque black box.
const boxOptions = {
  "sub-color": "#FFFFFFFF",
  "sub-back-color": "#99000000",
  "sub-shadow-offset": "6",
  "sub-border-size": "0"
} as const;

export class SubtitleStyle {
  private original?: Map<string, string>;
  private applied?: Map<string, string>;

  constructor(private readonly mpv: MpvOptionAccess) {}

  enable() {
    if (this.original) return;
    const original = new Map<string, string>();
    for (const name of Object.keys(boxOptions)) {
      const value = this.mpv.getString(`options/${name}`);
      if (!value) throw new Error(`SUBTITLE_STYLE_UNAVAILABLE:${name}`);
      original.set(name, value);
    }
    this.original = original;
    try {
      for (const [name, value] of Object.entries(boxOptions)) this.mpv.set(`options/${name}`, value);
      this.applied = new Map([...original.keys()].map(name => [name, this.mpv.getString(`options/${name}`)]));
    } catch (error) {
      this.restore();
      throw error;
    }
  }

  restore() {
    if (!this.original) return;
    for (const [name, value] of this.original) {
      // A user's later style change takes precedence over our saved value.
      if (!this.applied || this.mpv.getString(`options/${name}`) === this.applied.get(name)) {
        this.mpv.set(`options/${name}`, value);
      }
    }
    this.original = undefined;
    this.applied = undefined;
  }
}

export const SUBTITLE_SIZE_MIN = 16;
export const SUBTITLE_SIZE_MAX = 96;
export function validSubtitleSize(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= SUBTITLE_SIZE_MIN && value <= SUBTITLE_SIZE_MAX
    ? value : undefined;
}

export class SubtitleSize {
  private original?: string;
  private applied?: string;
  constructor(private readonly mpv: MpvOptionAccess) {}

  current(): number {
    const value = Number(this.mpv.getString("options/sub-font-size"));
    return Number.isFinite(value) && value > 0 ? Math.min(SUBTITLE_SIZE_MAX, Math.max(SUBTITLE_SIZE_MIN, Math.round(value))) : 55;
  }

  apply(size: number) {
    if (validSubtitleSize(size) === undefined) throw new Error("INVALID_SUBTITLE_SIZE");
    if (this.original === undefined) {
      this.original = this.mpv.getString("options/sub-font-size");
      if (!this.original) { this.original = undefined; throw new Error("SUBTITLE_SIZE_UNAVAILABLE"); }
    }
    this.mpv.set("options/sub-font-size", String(size));
    this.applied = this.mpv.getString("options/sub-font-size");
  }

  restore() {
    if (this.original === undefined) return;
    if (this.mpv.getString("options/sub-font-size") === this.applied) {
      this.mpv.set("options/sub-font-size", this.original);
    }
    this.original = undefined;
    this.applied = undefined;
  }
}
