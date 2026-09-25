import { FormEvent, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';
import { applyTheme, readConfirmWritesUi, ThemeId, writeConfirmWritesUi } from '../theme';
import { BoardDetail, BoardSummary, ConnectorType, Stage } from '../types';
import { boardWriteGateEnabled } from '../writeGate';
import { ConnectorHealth } from './ConnectorHealth';

interface Props {
  board?: BoardDetail | null;
  onCreated: (boardId: string) => void;
  theme: ThemeId;
  onThemeChange: (theme: ThemeId) => void;
}

interface Preferences {
  use_system_proxy: boolean;
  proxy_env_detected: boolean;
  proxy_env: Record<string, string>;
}

async function setStagesConfirmWrites(stages: Stage[], enabled: boolean): Promise<void> {
  await Promise.all(stages.map((stage) => apiClient.put(`/stages/${stage.id}`, { confirm_writes: enabled })));
}

export function Settings({ board, onCreated, theme, onThemeChange }: Props) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [boardName, setBoardName] = useState('Delivery');
  const [workspacePath, setWorkspacePath] = useState('');
  const [gitUrl, setGitUrl] = useState('');
  const [confirmWrites, setConfirmWrites] = useState(() => (board ? boardWriteGateEnabled(board.stages) : readConfirmWritesUi()));
  const [showForm, setShowForm] = useState(false);
  const [formType, setFormType] = useState<ConnectorType | undefined>();
  const [gateError, setGateError] = useState('');
  const [proxyError, setProxyError] = useState('');

  const preferences = useQuery({
    queryKey: ['preferences'],
    queryFn: () => apiClient.get<Preferences>('/preferences')
  });

  useEffect(() => {
    if (board?.stages) {
      setConfirmWrites(boardWriteGateEnabled(board.stages));
    } else {
      setConfirmWrites(readConfirmWritesUi());
    }
  }, [board]);

  const createBoard = useMutation({
    mutationFn: async () => {
      const created = await apiClient.post<BoardSummary>('/boards', {
        name: boardName,
        description: 'Initial Norns board',
        workspace_path: workspacePath,
        git_url: gitUrl
      });
      const preferConfirm = readConfirmWritesUi();
      if (preferConfirm && created.stages?.length) {
        await setStagesConfirmWrites(created.stages, true);
      }
      return created;
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      setBoardName('Delivery');
      setWorkspacePath('');
      setGitUrl('');
      onCreated(created.id);
    }
  });

  const writeGate = useMutation({
    mutationFn: async (enabled: boolean) => {
      if (!board?.stages.length) {
        writeConfirmWritesUi(enabled);
        return enabled;
      }
      await setStagesConfirmWrites(board.stages, enabled);
      writeConfirmWritesUi(enabled);
      return enabled;
    },
    onSuccess: (enabled) => {
      setConfirmWrites(enabled);
      setGateError('');
      if (board) {
        queryClient.invalidateQueries({ queryKey: ['board', board.id] });
        queryClient.invalidateQueries({ queryKey: ['boards'] });
      }
    },
    onError: (error) => {
      setGateError(error instanceof Error ? error.message : 'Failed to update write gate');
    }
  });

  const systemProxy = useMutation({
    mutationFn: async (enabled: boolean) => apiClient.put<Preferences>('/preferences', { use_system_proxy: enabled }),
    onSuccess: (data) => {
      setProxyError('');
      queryClient.setQueryData(['preferences'], data);
    },
    onError: (error) => {
      setProxyError(error instanceof Error ? error.message : 'Failed to update proxy preference');
      queryClient.invalidateQueries({ queryKey: ['preferences'] });
    }
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (boardName) {
      createBoard.mutate();
    }
  };

  const useProxy = preferences.data?.use_system_proxy ?? true;
  const proxyKeys = preferences.data?.proxy_env ? Object.keys(preferences.data.proxy_env) : [];

  return (
    <div className="settings settings-page">
      <h1>{t('settings.title')}</h1>
      <p className="muted">{t('settings.intro')}</p>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">0</span>
          <h2 className="settings-section-title">{t('settings.newBoard')}</h2>
        </div>
        <p className="muted">{t('settings.newBoardHint')}</p>
        <form onSubmit={onSubmit}>
          <label className="field">
            {t('settings.boardName')}
            <input className="input" value={boardName} onChange={(event) => setBoardName(event.target.value)} placeholder="Board name" />
          </label>
          <details className="workspace-details">
            <summary>Git repo for this board (optional)</summary>
            <label className="field">
              Folder on this machine
              <input className="input" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="/home/you/projects/app" />
            </label>
            <label className="field">
              GitHub or git URL
              <input className="input" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/org/app" />
            </label>
          </details>
          <button type="submit" className="btn btn-primary" disabled={!boardName || createBoard.isPending}>
            {createBoard.isPending ? t('settings.creating') : t('settings.createBoard')}
          </button>
        </form>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">1</span>
          <h2 className="settings-section-title">{t('settings.sectionModels')}</h2>
        </div>
        <p className="muted">{t('settings.modelsIntro')}</p>
        <ConnectorHealth
          variant="models"
          preferredType={formType}
          showForm={showForm && (formType === 'openai' || formType === 'cursor' || formType === 'deepseek')}
          onShowFormChange={(open) => {
            setShowForm(open);
            if (!open) {
              setFormType(undefined);
            }
          }}
          onRequestConnect={(type) => {
            setFormType(type);
            setShowForm(true);
          }}
        />
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">2</span>
          <h2 className="settings-section-title">{t('settings.sectionConnectors')}</h2>
        </div>
        <p className="muted">{t('settings.toolsIntro')}</p>
        <ConnectorHealth
          variant="tools"
          preferredType={formType}
          showForm={showForm && formType !== 'openai' && formType !== 'cursor' && formType !== 'deepseek' && formType != null}
          onShowFormChange={(open) => {
            setShowForm(open);
            if (!open) {
              setFormType(undefined);
            }
          }}
          onRequestConnect={(type) => {
            setFormType(type);
            setShowForm(true);
          }}
        />
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">3</span>
          <h2 className="settings-section-title">{t('settings.sectionWriteGate')}</h2>
        </div>
        <p className="muted">{board ? t('settings.writeGateBoard', { name: board.name }) : t('settings.writeGateNoBoard')}</p>
        <div className="write-gate-row">
          <span aria-hidden="true">⚠</span>
          <span>{t('settings.writeGateLabel')}</span>
          <button
            type="button"
            className={`toggle${confirmWrites ? ' is-on' : ''}`}
            role="switch"
            aria-checked={confirmWrites}
            disabled={writeGate.isPending}
            onClick={() => {
              const next = !confirmWrites;
              setConfirmWrites(next);
              writeGate.mutate(next);
            }}
          >
            <i />
          </button>
        </div>
        <p className="muted settings-write-gate-hint">{t('settings.writeGateHint')}</p>
        {writeGate.isPending ? <p className="muted">{t('settings.writeGateUpdating')}</p> : null}
        {gateError ? <p className="error">{gateError}</p> : null}
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">4</span>
          <h2 className="settings-section-title">{t('settings.sectionNetwork')}</h2>
        </div>
        <div className="write-gate-row">
          <span aria-hidden="true">⇄</span>
          <span>{t('settings.proxyLabel')}</span>
          <button
            type="button"
            className={`toggle${useProxy ? ' is-on' : ''}`}
            role="switch"
            aria-checked={useProxy}
            disabled={preferences.isLoading || systemProxy.isPending}
            onClick={() => systemProxy.mutate(!useProxy)}
          >
            <i />
          </button>
        </div>
        <p className="muted settings-write-gate-hint">{t('settings.proxyHint')}</p>
        {preferences.data?.proxy_env_detected ? (
          <p className="muted">{t('settings.proxyDetected', { keys: proxyKeys.join(', ') })}</p>
        ) : (
          <p className="muted">{t('settings.proxyNone')}</p>
        )}
        {systemProxy.isPending ? <p className="muted">{t('settings.proxyUpdating')}</p> : null}
        {proxyError ? <p className="error">{proxyError}</p> : null}
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <span className="settings-section-num">5</span>
          <h2 className="settings-section-title">{t('settings.sectionAppearance')}</h2>
        </div>
        <div className="appearance-grid">
          <button
            type="button"
            className={`appearance-card${theme === 'command-light' ? ' is-selected' : ''}`}
            onClick={() => {
              onThemeChange('command-light');
              applyTheme('command-light');
            }}
          >
            <span aria-hidden="true">☀</span>
            <span>{t('settings.appearanceLight')}</span>
            {theme === 'command-light' ? <span className="appearance-card-check">✓</span> : null}
          </button>
          <button
            type="button"
            className={`appearance-card${theme === 'night' ? ' is-selected' : ''}`}
            onClick={() => {
              onThemeChange('night');
              applyTheme('night');
            }}
          >
            <span aria-hidden="true">☾</span>
            <span>{t('settings.appearanceNight')}</span>
            {theme === 'night' ? <span className="appearance-card-check">✓</span> : null}
          </button>
        </div>
      </section>
    </div>
  );
}
