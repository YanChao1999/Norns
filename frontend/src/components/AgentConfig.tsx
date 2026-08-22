import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
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
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>Agent config · {stage.name}</h3>
          <button onClick={onClose}>Close</button>
        </div>

        <label style={labelStyle}>
          System prompt
          <textarea
            rows={6}
            value={form.system_prompt}
            onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))}
          />
        </label>

        <label style={labelStyle}>
          Model
          <input value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} />
        </label>

        <label style={labelStyle}>
          Temperature
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={form.temperature}
            onChange={(event) => setForm((current) => ({ ...current, temperature: Number(event.target.value) }))}
          />
        </label>

        <div style={labelStyle}>
          <span>Tools</span>
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            {availableTools.map((tool) => {
              const checked = form.tool_allowlist.includes(tool);
              return (
                <label key={tool} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
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

        <button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save config'}
        </button>
      </div>
    </div>
  );
}

const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(17,24,39,0.45)',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  zIndex: 20
};

const modalStyle: CSSProperties = {
  width: 'min(720px, 92vw)',
  background: 'white',
  borderRadius: 12,
  padding: 24,
  display: 'grid',
  gap: 16
};

const labelStyle: CSSProperties = {
  display: 'grid',
  gap: 8
};
