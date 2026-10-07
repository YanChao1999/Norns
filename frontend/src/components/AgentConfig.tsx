import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Stage } from '../types';
import { Dialog } from './Dialog';

const FALLBACK_PLUGINS = ['norns', 'sandbox', 'abom', 'github', 'jira', 'polarion'];

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
    staleTime: 30_000,
    refetchOnMount: 'always'
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
      const isLegacyCursorGpt4o = savedModel === 'gpt-4o' && savedProvider === 'cursor';
      const isUnboundGpt4o = savedModel === 'gpt-4o' && !savedProvider;
      // Keep explicit provider-bound choices (including OpenAI gpt-4o). Only rewrite
      // unbound board defaults and Cursor-bound legacy gpt-4o.
      if (savedProvider && savedModel && !isLegacyCursorGpt4o) {
        return current;
      }
      if (isLegacyCursorGpt4o || isUnboundGpt4o || (!savedProvider && current.model === preferred.id)) {
        const next = isLegacyCursorGpt4o
          ? entries.find((entry) => entry.usable && entry.provider === 'cursor' && entry.id === 'auto') ||
            entries.find((entry) => entry.usable && entry.provider === 'cursor') ||
            preferred
          : preferred;
        if (current.model === next.id && current.llm_provider === next.provider) {
          return current;
        }
        return { ...current, model: next.id, llm_provider: next.provider };
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
            ? [
                catalog.source === 'api' || catalog.source === 'mixed'
                  ? `Loaded ${options.length} model${options.length === 1 ? '' : 's'} from connector APIs for real agent runs.`
                  : `Using curated fallback models (${options.length}). Fix the connector key or network to load the live API catalog.`,
                catalog.error ? catalog.error : ''
              ]
                .filter(Boolean)
                .join(' ')
            : 'Add a DeepSeek, OpenAI, or Cursor connector in Settings to load models.'}
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
        <span>Different git folder for this column</span>
        <p className="muted">
          Leave blank to use the board repo
          {boardWorkspace?.git_url || boardWorkspace?.path ? ` (${boardWorkspace.git_url || boardWorkspace.path}).` : '.'} Only fill this in if this stage
          should work in another project.
        </p>
        <label className="field">
          Folder on this machine
          <input
            className="input"
            value={form.workspace_path}
            onChange={(event) => setForm((current) => ({ ...current, workspace_path: event.target.value }))}
            placeholder={boardWorkspace?.path || 'Same as the board'}
          />
        </label>
        <label className="field">
          GitHub or git URL
          <input
            className="input"
            value={form.git_url}
            onChange={(event) => setForm((current) => ({ ...current, git_url: event.target.value }))}
            placeholder={boardWorkspace?.git_url || 'Same as the board'}
          />
        </label>
      </div>

      <div className="field">
        <span>Plugins / MCP — empty allowlist grants none</span>
        <p className="muted">
          Enable norns (cards, stages, prompts, git workspace), sandbox (reproduce / env-build), abom (skill store from{' '}
          <a href="https://yanchao1999.github.io/abom/" target="_blank" rel="noreferrer">
            abom
          </a>
          ), github, jira, polarion, or an MCP connector from Settings. Cursor stages receive these as MCP servers; OpenAI/DeepSeek stages use the same tools as
          functions. Confirm writes is per stage on Machine, not bound to column names.
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
                {plugin && !plugin.available ? (tool === 'abom' ? ' (install abom CLI)' : ' (no connector)') : ''}
              </label>
            );
          })}
        </div>
      </div>

      <AbomMaterials
        workspacePath={form.workspace_path || boardWorkspace?.path || ''}
        abomEnabled={form.tool_allowlist.includes('abom')}
        abomAvailable={Boolean(plugins.find((item) => item.name === 'abom')?.available)}
        onEnableAbom={() =>
          setForm((current) => (current.tool_allowlist.includes('abom') ? current : { ...current, tool_allowlist: [...current.tool_allowlist, 'abom'] }))
        }
      />

      <button type="button" className="btn btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
        {mutation.isPending ? 'Saving…' : 'Save config'}
      </button>
    </Dialog>
  );
}

type RecipeKind = 'skill' | 'prompt' | 'mcp' | 'package' | '';

interface RecipeCard {
  name: string;
  kind: string;
  description: string;
  homepage: string;
  license: string;
  git: string;
  ref: string;
  path: string | null;
  installed: boolean;
  linked: boolean;
  enabled: boolean;
}

function AbomMaterials({
  workspacePath,
  abomEnabled,
  abomAvailable,
  onEnableAbom
}: {
  workspacePath: string;
  abomEnabled: boolean;
  abomAvailable: boolean;
  onEnableAbom: () => void;
}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<RecipeKind>('skill');
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const { data: status } = useQuery({
    queryKey: ['abom-status'],
    queryFn: () => apiClient.get<{ installed: boolean; homepage: string; install: string; kinds?: string[] }>('/abom/status'),
    staleTime: 60_000
  });

  const catalogParams = new URLSearchParams();
  if (query.trim()) {
    catalogParams.set('query', query.trim());
  }
  if (kind) {
    catalogParams.set('kind', kind);
  }
  if (workspacePath) {
    catalogParams.set('workspace_path', workspacePath);
  }
  const catalogQs = catalogParams.toString();

  const { data: catalog, refetch: refetchCatalog } = useQuery({
    queryKey: ['abom-catalog', query, kind, workspacePath],
    enabled: abomAvailable,
    queryFn: () => apiClient.get<{ recipes: RecipeCard[]; count: number; kinds: string[] }>(`/abom/catalog${catalogQs ? `?${catalogQs}` : ''}`)
  });

  const enableRecipe = async (recipe: RecipeCard) => {
    setBusy(recipe.name);
    setMessage(null);
    try {
      const result = await apiClient.post<{
        name: string;
        installed: boolean;
        linked: boolean;
        text: string;
      }>('/abom/enable', {
        name: recipe.name,
        target_repo: workspacePath || null
      });
      onEnableAbom();
      if (result.linked) {
        setMessage(`Enabled ${recipe.name} for this board. Save config to keep the abom plugin on.`);
      } else if (result.installed) {
        setMessage(`Installed ${recipe.name}. Bind a board git folder, then Enable again to link it into .abom/.`);
      } else {
        setMessage(result.text);
      }
      void refetchCatalog();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
    setBusy(null);
  };

  const kinds: Array<{ id: RecipeKind; label: string }> = [
    { id: 'skill', label: 'Skills' },
    { id: 'mcp', label: 'MCP' },
    { id: 'prompt', label: 'Prompts' },
    { id: 'package', label: 'Packages' },
    { id: '', label: 'All' }
  ];

  return (
    <div className="field abom-materials">
      <span>Skill store (abom)</span>
      <p className="muted">
        Browse GitHub-backed recipes from{' '}
        <a href={status?.homepage || 'https://yanchao1999.github.io/abom/'} target="_blank" rel="noreferrer">
          abom
        </a>
        . <strong>Enable</strong> installs from the catalog and links into the board folder&apos;s <code>.abom/</code> so skills load into the stage prompt (MCP
        recipes attach for Cursor stages).
      </p>
      {!abomAvailable ? (
        <p className="muted">CLI missing. {status?.install || 'pip install git+https://github.com/YanChao1999/abom.git'} then restart Norns.</p>
      ) : null}
      {!abomEnabled ? <p className="muted">Enabling a recipe also turns on the abom plugin for this column (save config to keep it).</p> : null}
      {!workspacePath ? <p className="muted">Bind a board git folder so Enable can link skills into that checkout.</p> : null}
      <div className="abom-kind-tabs" role="tablist" aria-label="Recipe kind">
        {kinds.map((item) => (
          <button
            key={item.label}
            type="button"
            role="tab"
            aria-selected={kind === item.id}
            className={`btn btn-ghost btn-compact${kind === item.id ? ' is-active' : ''}`}
            onClick={() => setKind(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <label className="field">
        Search store
        <input className="input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="name or description…" />
      </label>
      {abomAvailable ? (
        <ul className="abom-store-list">
          {(catalog?.recipes || []).slice(0, 20).map((recipe) => {
            const github = recipe.git.replace(/\.git$/, '').replace(/^git@github\.com:/, 'https://github.com/');
            const enabled = recipe.enabled || recipe.linked;
            return (
              <li key={recipe.name} className="abom-store-card">
                <div className="abom-store-card-body">
                  <div className="abom-store-card-head">
                    <strong>{recipe.name}</strong>
                    <span className="abom-kind-chip">{recipe.kind}</span>
                    {enabled ? <span className="abom-status-chip is-on">enabled</span> : null}
                    {!enabled && recipe.installed ? <span className="abom-status-chip">installed</span> : null}
                  </div>
                  <p>{recipe.description}</p>
                  <p className="muted abom-store-meta">
                    {recipe.license}
                    {' · '}
                    <a href={recipe.homepage || github} target="_blank" rel="noreferrer">
                      source
                    </a>
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-compact"
                  disabled={busy === recipe.name || enabled}
                  onClick={() => void enableRecipe(recipe)}
                >
                  {busy === recipe.name ? '…' : enabled ? 'Enabled' : 'Enable'}
                </button>
              </li>
            );
          })}
          {catalog && catalog.recipes.length === 0 ? <li className="muted">No recipes match this filter.</li> : null}
        </ul>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
    </div>
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
