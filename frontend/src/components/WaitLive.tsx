import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { DEFAULT_CURSOR_TIMEOUT_MS, waitCopy } from '../waitProgress';

interface Props {
  startedAt?: string | null;
  variant?: 'card' | 'banner' | 'footer';
  timeoutMs?: number;
}

function useCursorTimeoutMs(overrideMs?: number): number {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.get<{ cursor_timeout_seconds?: number }>('/health'),
    staleTime: 60_000
  });
  if (typeof overrideMs === 'number' && overrideMs > 0) {
    return overrideMs;
  }
  const seconds = data?.cursor_timeout_seconds;
  if (typeof seconds === 'number' && seconds > 0) {
    return Math.round(seconds * 1000);
  }
  return DEFAULT_CURSOR_TIMEOUT_MS;
}

export function WaitLive({ startedAt, variant = 'card', timeoutMs }: Props) {
  const limitMs = useCursorTimeoutMs(timeoutMs);
  const [now, setNow] = useState(() => Date.now());
  const startMs = useMemo(() => {
    const parsed = startedAt ? Date.parse(startedAt) : Number.NaN;
    return Number.isNaN(parsed) ? Date.now() : parsed;
  }, [startedAt]);

  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startMs]);

  const copy = waitCopy(now - startMs, limitMs);

  if (variant === 'footer') {
    return (
      <span className="wait-live" role="status">
        {copy.title} · {copy.elapsedLabel}
      </span>
    );
  }

  if (variant === 'banner') {
    return (
      <p className="notice wait-banner" role="status">
        <strong>
          {copy.title} · {copy.elapsedLabel}
        </strong>
        <span>{copy.detail}</span>
        <span className="wait-track" aria-hidden="true">
          <i />
        </span>
      </p>
    );
  }

  return (
    <div className="card-live is-wait">
      {copy.title} · {copy.elapsedLabel}
    </div>
  );
}
