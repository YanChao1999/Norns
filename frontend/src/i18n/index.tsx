import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from 'react';

import { en, MessageKey, Messages } from './en';

export type LocaleId = 'en';

const CATALOG: Record<LocaleId, Messages> = {
  en
};

const STORAGE_KEY = 'norns.locale';

interface LocaleContextValue {
  locale: LocaleId;
  setLocale: (locale: LocaleId) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readStoredLocale(): LocaleId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'en') {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return 'en';
}

function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, name: string) => (vars[name] != null ? String(vars[name]) : `{${name}}`));
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleId>(readStoredLocale);

  const setLocale = useCallback((next: LocaleId) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => {
      const catalog = CATALOG[locale] ?? CATALOG.en;
      return format(catalog[key] ?? CATALOG.en[key] ?? key, vars);
    },
    [locale]
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error('useI18n must be used within LocaleProvider');
  }
  return ctx;
}

/** Non-hook translator for modules that already have English defaults (tests / helpers). */
export function tEn(key: MessageKey, vars?: Record<string, string | number>): string {
  return format(en[key] ?? key, vars);
}

export type { MessageKey };
