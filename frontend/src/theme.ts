export type ThemeId = 'command-light' | 'night';

export const THEME_STORAGE_KEY = 'norns.theme';
export const CONFIRM_WRITES_UI_KEY = 'norns.confirmWritesUi';

export function readTheme(): ThemeId {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === 'command-light' || raw === 'night') {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return 'command-light';
}

export function applyTheme(theme: ThemeId): void {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}

export function readConfirmWritesUi(): boolean {
  try {
    const raw = localStorage.getItem(CONFIRM_WRITES_UI_KEY);
    if (raw === null) {
      return true;
    }
    return raw === '1' || raw === 'true';
  } catch {
    return true;
  }
}

export function writeConfirmWritesUi(enabled: boolean): void {
  try {
    localStorage.setItem(CONFIRM_WRITES_UI_KEY, enabled ? '1' : '0');
  } catch {
    /* ignore */
  }
}
