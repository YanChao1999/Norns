import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Stage } from '../types';
import { Dialog } from './Dialog';

const FALLBACK_PLUGINS = ['norns', 'github', 'jira', 'polarion'];

interface PluginInfo {
  name: string;
  title: string;
  description: string;
  builtin: boolean;
  requires_connector: string | null;
  available: boolean;
}

interface LlmModelEntry {
  id: string;
  provider: string;
  label: string;
  usable: boolean;
  source: string;
}

interface LlmModelCatalog {
  provider: string;
  default_model: string;
  models: string[];
  source: string;
  error?: string;
  entries?: LlmModelEntry[];
}

interface Props {
  stage: Stage | null;
  boardWorkspace?: { path: string; git_url: string };
  onClose: () => void;
}

function selectionKey(provider: string, model: string): string {
  return `${provider}::${model}`;
}

function parseSelection(value: string): { llm_provider: string; model: string } {
  const split = value.indexOf('::');
  if (split <= 0) {
    return { llm_provider: '', model: value };
  }
  return { llm_provider: value.slice(0, split), model: value.slice(split + 2) };
}

export function AgentConfigModal({ stage, boardWorkspace, onClose }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => initialForm(stage));

  useEffect(() => {
    setForm(initialForm(stage));
  }, [stage]);

  const { data: catalog, isLoading: modelsLoading } = useQuery({
    queryKey: ['llm-models'],
    enabled: Boolean(stage),
    queryFn: () => apiClient.get<LlmModelCatalog>('/connectors/llm-models'),
    staleTime: 60_000
  });
  const { data: plugins = [] } = useQuery({
    queryKey: ['plugins'],
    enabled: Boolean(stage),
    queryFn: () => apiClient.get<PluginInfo[]>('/plugins')
  });
  const availableTools = plugins.length ? plugins.map((plugin) => plugin.name) : FALLBACK_PLUGINS;

  const entries = useMemo(() => {
    const fromApi = catalog?.entries ?? [];
    if (!fromApi.length && catalog?.models?.length) {
      return catalog.models.map((id) => ({
        id,
        provider: catalog.provider,
        label: `${id} · ${catalog.provider}`,
        usable: true,
        source: catalog.source
      }));
    }
    return fromApi;
  }, [catalog]);

  const selection = selectionKey(form.llm_provider || catalog?.provider || '', form.model);
  const options = useMemo(() => {
    const list = [...entries];
    if (form.model) {
      const exists = list.some((entry) => entry.id === form.model && (!form.llm_provider || entry.provider === form.llm_provider));
      if (!exists) {
        list.unshift({
          id: form.model,
          provider: form.llm_provider || catalog?.provider || '',
          label: form.llm_provider ? `${form.model} · ${form.llm_provider}` : form.model,
          usable: true,
          source: 'saved'
        });
      }
    }
    return list;
  }, [catalog?.provider, entries, form.llm_provider, form.model]);

  useEffect(() => {
    if (!catalog || !stage) {
      return;
    }
    const preferred =
      entries.find((entry) => entry.usable && entry.provider === catalog.provider && entry.id === catalog.default_model) ||
      entries.find((entry) => entry.usable && entry.provider === catalog.provider) ||
      entries.find((entry) => entry.usable);
    if (!preferred) {
      return;
    }
    setForm((current) => {
      const savedProvider = stage.agent_config?.llm_provider?.trim() || '';
      const savedModel = stage.agent_config?.model || '';
      // Keep an explicit user/provider-bound choice.
      if (savedProvider && savedModel && savedModel !== 'gpt-4o') {
        return current;
      }
      // Upgrade legacy gpt-4o defaults to the active provider’s default, labeled by API.
      if (!savedProvider && (current.model === 'gpt-4o' || current.model === preferred.id)) {
        if (current.model === preferred.id && current.llm_provider === preferred.provider) {
          return current;
        }
        return { ...current, model: preferred.id, llm_provider: preferred.provider };
      }
      if (!current.llm_provider && preferred.provider) {
        return { ...current, llm_provider: preferred.provider };
      }
      return current;
    });
  }, [catalog, entries, stage]);

  const mutation = useMutation({
    mutationFn: async () =>
      apiClient.put(`/stages/${stage?.id}`, {
        system_prompt: form.system_prompt,
        model: form.model,
        llm_provider: form.llm_provider,
        temperature: form.temperature,
        tool_allowlist: form.tool_allowlist,
        workspace_path: form.workspace_path,
        git_url: form.git_url
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', stage?.board_id] });
      onClose();
    }
  });

  if (!stage) {
    return null;
  }

  return (
    <Dialog open onClose={onClose} labelledBy="agent-config-title" variant="modal">
      <div className="modal-head">
        <h2 id="agent-config-title">Agent config · {stage.name}</h2>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Close
        </button>
      </div>

      <label className="field">
        System prompt
        <textarea
          className="textarea"
          rows={6}
          value={form.system_prompt}
          onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))}
        />
      </label>
      {stage.require_approval ? (
        <p className="muted">Human gate is on. The runner asks this agent for DECISION: approve or reject. A human still confirms in the card drawer.</p>
      ) : null}

      <label className="field">
        Model
        {options.length ? (
          <select
            className="input"
            value={options.some((entry) => selectionKey(entry.provider, entry.id) === selection) ? selection : selectionKey(options[0].provider, options[0].id)}
            onChange={(event) => {
              const next = parseSelection(event.target.value);
              setForm((current) => ({ ...current, model: next.model, llm_provider: next.llm_provider }));
            }}
            disabled={modelsLoading}
          >
            {options.map((entry) => (
              <option key={selectionKey(entry.provider, entry.id)} value={selectionKey(entry.provider, entry.id)} disabled={!entry.usable}>
                {entry.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="input"
            value={form.model}
            onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
            placeholder={modelsLoading ? 'Loading models…' : 'model id'}
          />
        )}
      </label>
      <p className="muted">
        {modelsLoading
          ? 'Loading models from your LLM connectors…'
          : catalog
            ? `Models are labeled by API (e.g. auto · Cursor vs deepseek-v4-flash · DeepSeek). ${catalog.error ? catalog.error : ''}`.trim()
            : 'Add a DeepSeek or OpenAI connector in Settings to load models.'}
      </p>

      <label className="field">
        Temperature
        <input
          className="input"
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={form.temperature}
          onChange={(event) => setForm((current) => ({ ...current, temperature: Number(event.target.value) }))}
        />
      </label>

      <div className="field">
        <span>Git workspace for this agent</span>
        <p className="muted">
          Leave blank to use the board repo
          {boardWorkspace?.git_url || boardWorkspace?.path ? ` (${boardWorkspace.git_url || boardWorkspace.path}).` : '.'} Set a path here when this column
          should work in a different checkout.
        </p>
        <label className="field">
          Checkout path
          <input
            className="input"
            value={form.workspace_path}
            onChange={(event) => setForm((current) => ({ ...current, workspace_path: event.target.value }))}
            placeholder={boardWorkspace?.path || '/home/you/other-repo'}
          />
        </label>
        <label className="field">
          Git remote URL
          <input
            className="input"
            value={form.git_url}
            onChange={(event) => setForm((current) => ({ ...current, git_url: event.target.value }))}
            placeholder={boardWorkspace?.git_url || 'https://github.com/org/repo'}
          />
        </label>
      </div>

      <div className="field">
        <span>Plugins / MCP — empty allowlist grants none</span>
        <p className="muted">
          Enable norns (cards, stages, prompts, git workspace), github, jira, polarion, or an MCP connector from Settings. Cursor stages receive these as MCP
          servers; OpenAI/DeepSeek stages use the same tools as functions.
        </p>
        <div className="tool-row">
          {availableTools.map((tool) => {
            const plugin = plugins.find((item) => item.name === tool);
            const checked = form.tool_allowlist.includes(tool);
            return (
              <label key={tool} title={plugin?.description || tool}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() =>
                    setForm((current) => ({
                      ...current,
                      tool_allowlist: checked ? current.tool_allowlist.filter((item) => item !== tool) : [...current.tool_allowlist, tool]
                    }))
                  }
                />
                {plugin?.title || tool}
                {plugin && !plugin.available ? ' (no connector)' : ''}
              </label>
            );
          })}
        </div>
      </div>

      <button type="button" className="btn btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
        {mutation.isPending ? 'Saving…' : 'Save config'}
      </button>
    </Dialog>
  );
}

function initialForm(stage: Stage | null) {
  return {
    system_prompt: stage?.agent_config?.system_prompt ?? 'You are the stage agent. Produce a concise handoff for the next stage.',
    model: stage?.agent_config?.model ?? 'gpt-4o',
    llm_provider: stage?.agent_config?.llm_provider ?? '',
    temperature: stage?.agent_config?.temperature ?? 0.7,
    tool_allowlist: stage?.agent_config?.tool_allowlist ?? [],
    workspace_path: stage?.agent_config?.workspace_path ?? '',
    git_url: stage?.agent_config?.git_url ?? ''
  };
}
