// Where an installed Cue lives, and how the plugin starts its helper.
// IINA's utils.exec keeps only LC_ALL in the environment, so the plugin
// cannot read HOME. file.exists and resolvePath expand a leading ~/.
// Development mode keeps the baked launcher. Installed mode never executes
// a file shipped inside the plugin package.

export const INSTALLED_SUPPORT = "~/Library/Application Support/Cue";

export interface LaunchInput {
  preference: unknown;
  devBootstrap: string;
  exists: (path: string) => boolean;
  resolve: (path: string) => string | null;
}

export interface LaunchPlan {
  file: string;
  args: string[];
  /** Only an installed runtime is ever replaced by a newer one; a chosen helper or a checkout is not. */
  mode: "preference" | "installed" | "development";
}

export function planLaunch(input: LaunchInput): LaunchPlan {
  const preference = typeof input.preference === "string" ? input.preference.trim() : "";
  if (preference) {
    if (!preference.startsWith("/") || !input.exists(preference)) throw new Error("SETUP_REQUIRED");
    return {file: preference, args: ["ensure"], mode: "preference"};
  }
  const marker = `${INSTALLED_SUPPORT}/installed`;
  if (input.exists(marker)) {
    const launcher = `${INSTALLED_SUPPORT}/runtime/bin/cue-helper`;
    const python = `${INSTALLED_SUPPORT}/runtime/python/bin/python3.12`;
    if (input.exists(launcher)) {
      const absolute = input.resolve(launcher);
      // Arguments are not tilde-expanded. /bin/sh needs the absolute script.
      if (absolute && absolute.startsWith("/")) return {file: "/bin/sh", args: [absolute, "ensure"], mode: "installed"};
      return {file: launcher, args: ["ensure"], mode: "installed"};
    }
    if (input.exists(python)) {
      const absolute = input.resolve(python);
      if (absolute && absolute.startsWith("/")) return {file: absolute, args: ["-m", "cue.cli", "ensure"], mode: "installed"};
      return {file: python, args: ["-m", "cue.cli", "ensure"], mode: "installed"};
    }
    throw new Error("SETUP_REQUIRED");
  }
  if (!input.devBootstrap.startsWith("/") || !input.exists(input.devBootstrap)) throw new Error("SETUP_REQUIRED");
  return {file: input.devBootstrap, args: ["ensure"], mode: "development"};
}
