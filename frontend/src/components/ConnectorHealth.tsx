import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Connector, ConnectorType } from '../types';

const TYPES: ConnectorType[] = ['openai', 'cursor', 'deepseek', 'github', 'jira', 'polarion'];

const LLM_DEFAULTS: Record<'openai' | 'cursor' | 'deepseek', { base_url: string; default_model: string; placeholder: string }> = {
  openai: { base_url: 'https://api.openai.com/v1', default_model: 'gpt-4o', placeholder: 'sk-…' },
  cursor: { base_url: 'https://api.cursor.com/v1', default_model: 'auto', placeholder: 'crsr_…' },
  deepseek: { base_url: 'https://api.deepseek.com/v1', default_model: 'deepseek-v4-flash', placeholder: 'sk-…' }
};

const EMPTY_FORM = {
  name: 'OpenAI',
  connector_type: 'openai' as ConnectorType,
  is_active: true,
  api_key: '',
  base_url: LLM_DEFAULTS.openai.base_url,
  default_model: LLM_DEFAULTS.openai.default_model,
  token: '',
  server: '',
  username: '',
  password: '',
  project: ''
};

export function ConnectorHealth() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const { data = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiClient.get<Connector[]>('/connectors')
  });

  const save = useMutation({
    mutationFn: async () => {
      const payload = { name: form.name, connector_type: form.connector_type, is_active: form.is_active, config: configFromForm(form) };
      if (editingId) {
        return apiClient.put<Connector>(`/connectors/${editingId}`, payload);
      }
      return apiClient.post<Connector>('/connectors', payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors'] });
      queryClient.invalidateQueries({ queryKey: ['health'] });
      setEditingId(null);
      setForm({ ...EMPTY_FORM, name: defaultName(form.connector_type), connector_type: form.connector_type, ...llmDefaults(form.connector_type) });
    }
  });

  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/connectors/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors'] });
      queryClient.invalidateQueries({ queryKey: ['health'] });
      setEditingId(null);
      setForm(EMPTY_FORM);
    }
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (form.name) {
      save.mutate();
    }
  };

  return (
    <section className="panel">
      <h2>Connectors</h2>
      <p className="muted">OpenAI, Cursor, and DeepSeek are model connectors. GitHub, Jira, and Polarion unlock tools on a column when you check them under Agent. If more than one model connector is active, Cursor is used first, then DeepSeek, then OpenAI.</p>

      <form className="connector-form" onSubmit={onSubmit}>
        <label className="field">
          Type
          <select
            className="input"
            value={form.connector_type}
            onChange={(event) => {
              const connector_type = event.target.value as ConnectorType;
              setForm((current) => ({
                ...current,
                connector_type,
                name: editingId ? current.name : defaultName(connector_type),
                ...llmDefaults(connector_type)
              }));
            }}
          >
            {TYPES.map((type) => (
              <option key={type} value={type}>
                {labelFor(type)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Name
          <input className="input" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
        </label>
        {isLlmType(form.connector_type) ? (
          <>
            <label className="field">
              API key
              <input
                className="input"
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                placeholder={editingId ? 'Leave blank to keep the saved key' : LLM_DEFAULTS[form.connector_type].placeholder}
              />
            </label>
            <label className="field">
              Base URL
              <input className="input" value={form.base_url} onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))} />
            </label>
            <label className="field">
              Default model
              <input className="input" value={form.default_model} onChange={(event) => setForm((current) => ({ ...current, default_model: event.target.value }))} />
            </label>
          </>
        ) : null}
        {form.connector_type === 'github' ? (
          <>
            <label className="field">
              Token
              <input className="input" type="password" autoComplete="off" value={form.token} onChange={(event) => setForm((current) => ({ ...current, token: event.target.value }))} placeholder={editingId ? 'Leave blank to keep the saved token' : ''} />
            </label>
            <label className="field">
              Base URL (optional)
              <input className="input" value={form.base_url} onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))} placeholder="https://api.github.com" />
            </label>
          </>
        ) : null}
        {form.connector_type === 'jira' ? (
          <>
            <label className="field">
              Server
              <input className="input" value={form.server} onChange={(event) => setForm((current) => ({ ...current, server: event.target.value }))} placeholder="https://jira.example.com" />
            </label>
            <label className="field">
              Username
              <input className="input" value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} />
            </label>
            <label className="field">
              Token
              <input className="input" type="password" autoComplete="off" value={form.token} onChange={(event) => setForm((current) => ({ ...current, token: event.target.value }))} placeholder={editingId ? 'Leave blank to keep the saved token' : ''} />
            </label>
          </>
        ) : null}
        {form.connector_type === 'polarion' ? (
          <>
            <label className="field">
              Server
              <input className="input" value={form.server} onChange={(event) => setForm((current) => ({ ...current, server: event.target.value }))} />
            </label>
            <label className="field">
              Username
              <input className="input" value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} />
            </label>
            <label className="field">
              Password
              <input className="input" type="password" autoComplete="off" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} placeholder={editingId ? 'Leave blank to keep the saved password' : ''} />
            </label>
            <label className="field">
              Project (optional)
              <input className="input" value={form.project} onChange={(event) => setForm((current) => ({ ...current, project: event.target.value }))} />
            </label>
          </>
        ) : null}
        <label className="field">
          <span className="check-row">
            <input type="checkbox" checked={form.is_active} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} />
            Active
          </span>
        </label>
        {save.isError ? <div className="error">{saveError(save.error)}</div> : null}
        <div className="connector-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!form.name || save.isPending || (isLlmType(form.connector_type) && !editingId && !form.api_key.trim())}
          >
            {save.isPending ? 'Saving…' : editingId ? 'Save connector' : 'Add connector'}
          </button>
          {editingId ? (
            <button
              type="button"
              className="btn"
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>

      {isLoading ? <div className="muted">Loading connectors…</div> : null}
      {data.map((connector) => (
        <div key={connector.id} className="connector-row">
          <span>
            {connector.name} · {labelFor(connector.connector_type)}
            {connector.config_keys.includes('api_key') ? ' · key saved' : null}
          </span>
          <span className="connector-actions">
            <span className={connector.is_active ? 'is-active-text' : 'is-inactive-text'}>{connector.is_active ? 'active' : 'inactive'}</span>
            <button type="button" className="btn btn-ghost" onClick={() => startEdit(connector, setEditingId, setForm)}>
              Edit
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => remove.mutate(connector.id)} disabled={remove.isPending}>
              Remove
            </button>
          </span>
        </div>
      ))}
      {!data.length && !isLoading ? <div className="muted">No connectors yet. Add OpenAI, Cursor, or DeepSeek here so stage runs call a real model.</div> : null}
    </section>
  );
}

function isLlmType(type: ConnectorType): type is 'openai' | 'cursor' | 'deepseek' {
  return type === 'openai' || type === 'cursor' || type === 'deepseek';
}

function llmDefaults(type: ConnectorType): { base_url: string; default_model: string } {
  if (isLlmType(type)) {
    const defaults = LLM_DEFAULTS[type];
    return { base_url: defaults.base_url, default_model: defaults.default_model };
  }
  return { base_url: '', default_model: '' };
}

function defaultName(type: ConnectorType): string {
  return labelFor(type);
}

function labelFor(type: ConnectorType): string {
  if (type === 'openai') return 'OpenAI';
  if (type === 'cursor') return 'Cursor';
  if (type === 'deepseek') return 'DeepSeek';
  if (type === 'github') return 'GitHub';
  if (type === 'jira') return 'Jira';
  return 'Polarion';
}

function configFromForm(form: typeof EMPTY_FORM): Record<string, string> {
  if (isLlmType(form.connector_type)) {
    return { api_key: form.api_key, base_url: form.base_url, default_model: form.default_model };
  }
  if (form.connector_type === 'github') {
    return { token: form.token, base_url: form.base_url };
  }
  if (form.connector_type === 'jira') {
    return { server: form.server, username: form.username, token: form.token };
  }
  return { server: form.server, username: form.username, password: form.password, project: form.project };
}

function startEdit(connector: Connector, setEditingId: (id: string) => void, setForm: (form: typeof EMPTY_FORM) => void): void {
  const publicConfig = connector.public_config ?? {};
  const defaults = llmDefaults(connector.connector_type);
  setEditingId(connector.id);
  setForm({
    ...EMPTY_FORM,
    name: connector.name,
    connector_type: connector.connector_type,
    is_active: connector.is_active,
    base_url: publicConfig.base_url ?? defaults.base_url,
    default_model: publicConfig.default_model ?? defaults.default_model,
    server: publicConfig.server ?? '',
    username: publicConfig.username ?? '',
    project: publicConfig.project ?? ''
  });
}

function saveError(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Could not save connector.';
  }
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    /* raw */
  }
  return error.message || 'Could not save connector.';
}
