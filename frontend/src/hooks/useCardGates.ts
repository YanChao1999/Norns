import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';

function gateComment(approved: boolean, recommendation: 'approve' | 'reject' | null): string {
  if (recommendation && ((approved && recommendation === 'approve') || (!approved && recommendation === 'reject'))) {
    return `Confirmed agent recommendation: ${recommendation}`;
  }
  return approved ? 'Approved' : 'Rejected';
}

export function useCardGates(cardId: string | undefined, boardId: string | undefined) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    if (boardId) {
      queryClient.invalidateQueries({ queryKey: ['board', boardId] });
    }
    if (cardId) {
      queryClient.invalidateQueries({ queryKey: ['runs', cardId] });
    }
  };

  const approval = useMutation({
    mutationFn: async (input: { approved: boolean; recommendation?: 'approve' | 'reject' | null }) =>
      apiClient.post(`/cards/${cardId}/approve`, {
        approved: input.approved,
        comment: gateComment(input.approved, input.recommendation ?? null)
      }),
    onSuccess: invalidate
  });

  const writes = useMutation({
    mutationFn: async (approved: boolean) =>
      apiClient.post(`/cards/${cardId}/approve-writes`, {
        approved,
        comment: approved ? 'Confirmed pending writes' : 'Declined pending writes'
      }),
    onSuccess: invalidate
  });

  return { approval, writes };
}
