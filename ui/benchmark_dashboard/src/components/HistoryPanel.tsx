import type { HistoryEntrySummary } from '../types';

interface HistoryPanelProps {
  entries?: HistoryEntrySummary[];
}

export function HistoryPanel({ entries }: HistoryPanelProps) {
  const safeEntries = entries ?? [];
  return (
    <section className="card">
      <h2>Playlist History</h2>
      <div className="timeline">
        {safeEntries.length === 0 && <p>No history snapshots captured yet.</p>}
        {safeEntries.map((entry) => (
          <div className="timeline-entry" key={entry.path}>
            <strong>{entry.playlist_id ?? 'Unknown playlist'}</strong>
            <div className="chip-row">
              <span className="chip">{entry.run_id}</span>
              <span className="chip">{entry.scenario_count ?? 0} scenarios</span>
            </div>
            <small>{entry.last_updated ?? 'timestamp unavailable'}</small>
            {entry.coverage_status && (
              <p>
                Coverage:{' '}
                {Object.entries(entry.coverage_status)
                  .map(([status, count]) => `${status}:${count}`)
                  .join(', ')}
              </p>
            )}
            <p className="text-muted">{entry.path}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
