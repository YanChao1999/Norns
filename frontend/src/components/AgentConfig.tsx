import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Stage } from '../types';

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

  useEffect(() => {
    if (!stage) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stage, onClose]);

  const isOpen = useMemo(() => Boolean(stage), [stage]);

  const mutation = useMutation({
    mutationFn: async () => apiClient.put(`/stages/${stage?.id}`, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', stage?.board_id] });
      onClose();
    }
  });

  if (!isOpen || !stage) {
    return null;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-config-title"
        onClick={(event) => event.stopPropagation()}
      >
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

        <label className="field">
          Model
          <input
            className="input"
            value={form.model}
            onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
          />
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
                        tool_allowlist: checked
                          ? current.tool_allowlist.filter((item) => item !== tool)
                          : [...current.tool_allowlist, tool]
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
      </div>
    </div>
  );
}
