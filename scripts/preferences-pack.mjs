/** Development packs show the Terminal steps. A general-user pack leaves them hidden. */
export function preferencesForPack(source, development) {
  if (!development) return source;
  return source.replace('id="dev-setup" hidden', 'id="dev-setup"');
}
