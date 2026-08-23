import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Stage } from '../types';
import { Dialog } from './Dialog';

const availableTools = ['github', 'jira', 'polarion'];

interface Props {
  stage: Stage | null;
  onClose: () => void;
}

export function AgentConfigModal({ stage, onClose }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => ({
    system_prompt: stage?.agent_config?.system_prompt ?? 'You are the stage agent. Produce a concise handoff for the next stage.',
    model: stage?.agent_config?.model ?? 'gpt-4o',
    temperature: stage?.agent_config?.temperature ?? 0.7,
    tool_allowlist: stage?.agent_config?.tool_allowlist ?? []
  }));

  useEffect(() => {
    setForm({
      system_prompt: stage?.agent_config?.system_prompt ?? 'You are the stage agent. Produce a concise handoff for the next stage.',
      model: stage?.agent_config?.model ?? 'gpt-4o',
      temperature: stage?.agent_config?.temperature ?? 0.7,
      tool_allowlist: stage?.agent_config?.tool_allowlist ?? []
    });
  }, [stage]);

  const mutation = useMutation({
    mutationFn: async () => apiClient.put(`/stages/${stage?.id}`, form),
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
        <input className="input" value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} />
      </label>

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
        <span>Tools — empty allowlist grants none</span>
        <div className="tool-row">
          {availableTools.map((tool) => {
            const checked = form.tool_allowlist.includes(tool);
            return (
              <label key={tool}>
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
                {tool}
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
