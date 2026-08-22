import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Connector } from '../types';

export function ConnectorHealth() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiClient.get<Connector[]>('/connectors')
  });

  return (
    <section className="panel">
      <h2>Connectors</h2>
      {isLoading ? <div className="muted">Loading connectors…</div> : null}
      {data.map((connector) => (
        <div key={connector.id} className="connector-row">
          <span>
            {connector.name} · {connector.connector_type}
          </span>
          <span className={connector.is_active ? 'is-active-text' : 'is-inactive-text'}>{connector.is_active ? 'active' : 'inactive'}</span>
        </div>
      ))}
      {!data.length && !isLoading ? <div className="muted">No connectors configured.</div> : null}
    </section>
  );
}
