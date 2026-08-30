import { CardStatus } from './types';

export const STATUS_LABEL: Record<CardStatus, string> = {
  idle: 'idle',
  running: 'running',
  waiting_approval: 'waiting',
  waiting_tool_approval: 'confirm write',
  waiting_join: 'joining',
  blocked: 'blocked',
  done: 'done'
};
