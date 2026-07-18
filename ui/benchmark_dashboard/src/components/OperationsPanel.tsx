import type { OperationsSummary, ReplayEvent, RemediationEvent } from '../types';

interface OperationsPanelProps {
  summary?: OperationsSummary;
  statusMessage?: string | null;
  statusError?: string | null;
}

const renderReplay = (event: ReplayEvent) => (
  <li key={event.id}>
    <strong>{event.scenario_id}</strong>
    <span className="chip">return {event.return_code ?? '—'}</span>
    <span className="chip">run {event.run_id ?? 'n/a'}</span>
    <span className="chip">{event.timestamp}</span>
  </li>
);

const renderRemediation = (event: RemediationEvent) => (
  <li key={event.id}>
    <strong>{event.scenario_id}</strong>
    <span className="chip">{event.action}</span>
    <span className={`chip ${event.status.toLowerCase()}`}>{event.status}</span>
    <span className="chip">{event.timestamp}</span>
  </li>
);

export function OperationsPanel({ summary, statusMessage, statusError }: OperationsPanelProps) {
  return (
    <section className="card">
      <h2>Operations Loop</h2>
      {!summary ? (
        <p>Awaiting replay + remediation telemetry.</p>
      ) : (
        <>
          <div className="chip-row">
            <span className="chip">Replays: {summary.replay_count ?? 0}</span>
            <span className="chip">Backlog: {summary.remediation_backlog ?? 0}</span>
            {typeof summary.remediation_total === 'number' && (
              <span className="chip">Remediations: {summary.remediation_total}</span>
            )}
            {summary.last_replay_timestamp && (
              <span className="chip">Last Replay: {summary.last_replay_timestamp}</span>
            )}
          </div>
          {(statusMessage || statusError) && (
            <p className={`status-text ${statusError ? 'error' : 'success'}`}>
              {statusError ?? statusMessage}
            </p>
          )}
          <div className="operations-lists">
            <div>
              <h3>Recent Replays</h3>
              {summary.recent_replays && summary.recent_replays.length > 0 ? (
                <ul>
                  {summary.recent_replays.slice(0, 4).map(renderReplay)}
                </ul>
              ) : (
                <p className="text-muted">No replay events yet.</p>
              )}
            </div>
            <div>
              <h3>Recent Remediations</h3>
              {summary.recent_remediations && summary.recent_remediations.length > 0 ? (
                <ul>
                  {summary.recent_remediations.slice(0, 4).map(renderRemediation)}
                </ul>
              ) : (
                <p className="text-muted">No remediation events yet.</p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
