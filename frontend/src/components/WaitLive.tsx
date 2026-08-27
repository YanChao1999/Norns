import { useEffect, useMemo, useState } from 'react';

import { waitCopy } from '../waitProgress';

interface Props {
  startedAt?: string | null;
  variant?: 'card' | 'banner' | 'footer';
}

export function WaitLive({ startedAt, variant = 'card' }: Props) {
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

  const copy = waitCopy(now - startMs);

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
