import { CardStatus } from '../types';

export const STATUS_LABEL: Record<CardStatus, string> = {
  idle: 'idle',
  running: 'running',
  waiting_approval: 'waiting',
  blocked: 'blocked',
  done: 'done'
};
