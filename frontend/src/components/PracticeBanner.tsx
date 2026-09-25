import { useI18n } from '../i18n';

interface BannerProps {
  onGoSettings: () => void;
  onContinue: () => void;
}

export function PracticeBanner({ onGoSettings, onContinue }: BannerProps) {
  const { t } = useI18n();
  return (
    <aside className="practice-banner" role="status">
      <div className="practice-banner-copy">
        <span className="practice-banner-icon" aria-hidden="true">
          🔒
        </span>
        <div>
          <h2>{t('practice.title')}</h2>
          <p>{t('practice.body')}</p>
        </div>
      </div>
      <div className="practice-banner-actions">
        <button type="button" className="btn btn-primary" onClick={onGoSettings}>
          {t('practice.goSettings')}
        </button>
        <button type="button" className="btn" onClick={onContinue}>
          {t('practice.continue')}
        </button>
      </div>
    </aside>
  );
}

export function PracticeCard() {
  const { t } = useI18n();
  return (
    <aside className="practice-float" aria-label={t('practice.cardTitle')}>
      <div className="practice-float-head">
        <span aria-hidden="true">🛡</span>
        <span>{t('practice.cardTitle')}</span>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {t('practice.cardBody')}
      </p>
      <div className="practice-float-actions">
        <button
          type="button"
          className="btn btn-approve"
          onClick={() => {
            /* practice-only affordance — no API write */
          }}
        >
          {t('practice.approve')}
        </button>
        <span className="muted">{t('practice.approveHint')}</span>
      </div>
    </aside>
  );
}
