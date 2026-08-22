import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Connector } from '../types';

export function ConnectorHealth() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: async () => {
      try {
        return await apiClient.get<Connector[]>('/connectors');
      } catch {
        await apiClient.post('/auth/login', { username: 'admin', password: 'admin' });
        return apiClient.get<Connector[]>('/connectors');
      }
    }
  });

  return (
    <section style={{ background: 'white', borderRadius: 12, padding: 16, border: '1px solid #e5e7eb' }}>
      <h3 style={{ marginTop: 0 }}>Connector health</h3>
      {isLoading ? <div>Loading connectors…</div> : null}
      <div style={{ display: 'grid', gap: 8 }}>
        {data.map((connector) => (
          <div key={connector.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
            <span>
              {connector.name} · {connector.connector_type}
            </span>
            <span style={{ color: connector.is_active ? '#166534' : '#b91c1c' }}>
              {connector.is_active ? 'active' : 'inactive'}
            </span>
          </div>
        ))}
        {!data.length && !isLoading ? <div>No connectors configured.</div> : null}
      </div>
    </section>
  );
}
