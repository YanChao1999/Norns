import type { FormEvent } from 'react';
import { useState } from 'react';

import { apiClient } from '../api/client';

interface Props {
  onLoggedIn: (username: string) => void;
}

export function LoginForm({ onLoggedIn }: Props) {
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
      setError('Invalid username or password.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div>
          <p className="brand-sub">Norns</p>
          <h1>Control room</h1>
          <p>Sign in to operate boards and approval gates.</p>
        </div>
        <label className="field">
          Username
          <input
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="field">
          Password
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
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
