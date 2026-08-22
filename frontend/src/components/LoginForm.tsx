import type { CSSProperties, FormEvent } from 'react';
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
    <div style={pageStyle}>
      <form onSubmit={handleSubmit} style={formStyle}>
        <div>
          <h1 style={{ margin: '0 0 4px' }}>Norns</h1>
          <p style={{ margin: 0, color: '#475569' }}>Sign in to manage boards and approval gates.</p>
        </div>
        <label style={labelStyle}>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label style={labelStyle}>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <div style={{ color: '#b91c1c' }}>{error}</div> : null}
        <button type="submit" disabled={pending || !username || !password}>
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

const pageStyle: CSSProperties = {
  minHeight: '100vh',
  display: 'grid',
  placeItems: 'center',
  background: '#f1f5f9'
};

const formStyle: CSSProperties = {
  width: 'min(420px, 92vw)',
  background: 'white',
  borderRadius: 12,
  padding: 24,
  display: 'grid',
  gap: 16,
  border: '1px solid #e5e7eb'
};

const labelStyle: CSSProperties = {
  display: 'grid',
  gap: 8
};
