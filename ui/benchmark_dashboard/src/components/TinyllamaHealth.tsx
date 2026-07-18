interface TinyllamaHealthProps {
  snapshot?: {
    status_code?: number;
    latency_ms?: number;
    failure_reason?: string | null;
  };
}

export function TinyllamaHealth({ snapshot }: TinyllamaHealthProps) {
  return (
    <section className="card">
      <h2>TinyLLaMA Health</h2>
      {snapshot ? (
        <div className="stats-grid">
          <div className="stat">
            <div className="stat-label">Status Code</div>
            <div className="stat-value">{snapshot.status_code ?? '—'}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Latency (ms)</div>
            <div className="stat-value">{snapshot.latency_ms ?? '—'}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Failure Reason</div>
            <div className="stat-value">{snapshot.failure_reason ?? 'none'}</div>
          </div>
        </div>
      ) : (
        <p>No health snapshot recorded.</p>
      )}
    </section>
  );
}
