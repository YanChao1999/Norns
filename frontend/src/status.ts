import { CardStatus } from './types';
import { tEn } from './i18n';

export const STATUS_LABEL: Record<CardStatus, string> = {
  idle: tEn('status.idle'),
  running: tEn('status.running'),
  waiting_approval: tEn('status.waiting_approval'),
  waiting_tool_approval: tEn('status.waiting_tool_approval'),
  waiting_join: tEn('status.waiting_join'),
  blocked: tEn('status.blocked'),
  done: tEn('status.done')
};
