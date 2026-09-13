import type { FormEvent } from 'react';
import { useState } from 'react';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';

interface Props {
  onLoggedIn: (username: string) => void;
}

export function LoginForm({ onLoggedIn }: Props) {
  const { t } = useI18n();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const user = await apiClient.post<{ username: string }>('/auth/login', { username, password });
      onLoggedIn(user.username);
    } catch {
      setError(t('login.error'));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div>
          <p className="brand-sub">{t('login.brand')}</p>
          <h1>{t('login.title')}</h1>
          <p>{t('login.subtitle')}</p>
        </div>
        <label className="field">
          {t('login.username')}
          <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          {t('login.password')}
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button type="submit" className="btn btn-primary" disabled={pending || !username || !password}>
          {pending ? t('login.pending') : t('login.submit')}
        </button>
      </form>
    </div>
  );
}
