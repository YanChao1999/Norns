import { useCardGates } from '../hooks/useCardGates';
import { useI18n } from '../i18n';
import { SoftJoinProgress } from '../softJoin';
import { Card } from '../types';

interface Props {
  progress: SoftJoinProgress;
  onOpenCard?: (card: Card) => void;
}

export function SoftJoinBridge({ progress, onOpenCard }: Props) {
  const { t } = useI18n();
  const readyCard = progress.waitingWriteCard;
  const { writes } = useCardGates(readyCard?.id, readyCard?.board_id);
  const unlocked = Boolean(readyCard) && progress.complete;

  return (
    <aside className="soft-join" aria-label={t('board.softJoin')}>
      <div className="soft-join-badge">{t('board.softJoin')}</div>
      <p>
        {t('board.softJoinNeed', {
          settled: progress.settled,
          total: progress.total
        })}
      </p>
      <button
        type="button"
        className="btn btn-confirm-write"
        disabled={!unlocked || writes.isPending}
        onClick={() => {
          if (!readyCard) {
            return;
          }
          writes.mutate(true);
          onOpenCard?.(readyCard);
        }}
      >
        {unlocked ? t('board.confirmWrite') : t('board.confirmWriteWaiting')}
      </button>
    </aside>
  );
}
