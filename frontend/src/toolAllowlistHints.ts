/** First-run / Agent dialog hints for empty or unusable tool allowlists. */

export interface PluginAvailability {
  name: string;
  title?: string;
  available: boolean;
  requires_connector?: string | null;
}

export function isEmptyAllowlist(allowlist: string[] | null | undefined): boolean {
  return !allowlist?.length;
}

/** Plugins on the allowlist that cannot run (missing connector / CLI). */
export function unavailableAllowlisted(
  allowlist: string[] | null | undefined,
  plugins: PluginAvailability[]
): PluginAvailability[] {
  if (!allowlist?.length || !plugins.length) {
    return [];
  }
  const wanted = new Set(allowlist.map((name) => name.trim().toLowerCase()).filter(Boolean));
  return plugins.filter((plugin) => wanted.has(plugin.name.trim().toLowerCase()) && !plugin.available);
}

export function pluginNeedsConnector(plugin: PluginAvailability): boolean {
  return Boolean(plugin.requires_connector);
}
