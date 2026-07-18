import { useState, useCallback, useMemo } from 'react';
import { useDashboardData } from './hooks';
import { OverviewStats } from './components/OverviewStats';
import { ScenarioHighlights } from './components/ScenarioHighlights';
import { HistoryPanel } from './components/HistoryPanel';
import { TinyllamaHealth } from './components/TinyllamaHealth';
import { OperationsPanel } from './components/OperationsPanel';
import { FlowchartMacroBuilder } from './components/FlowchartMacroBuilder';
import { replayScenario, openRemediationTask, runRemediationPytest } from './api';

function HeroSection({ playlistId, runId, updated }: { playlistId?: string; runId?: string; updated?: string }) {
  return (
    <section className="card hero">
      <div>
        <h1>Benchmark Observatory</h1>
        <p>
          Live view of playlist telemetry, resolver coverage, and TinyLLaMA health. Consume the JSON-first
          evidence without spelunking logs.
        </p>
        <div className="chip-row">
          <span className="chip">Playlist: {playlistId ?? 'n/a'}</span>
          <span className="chip">Run: {runId ?? 'n/a'}</span>
          <span className="chip">Updated: {updated ?? '—'}</span>
        </div>
      </div>
      <div className="button-row">
        <button onClick={() => window.location.reload()}>Refresh</button>
        <button className="secondary" onClick={() => window.open('/api/dashboard', '_blank')?.focus()}>
          View JSON
        </button>
      </div>
    </section>
  );
}

export default function App() {
  const { data, loading, error, refresh } = useDashboardData();
  const [operationsStatus, setOperationsStatus] = useState<{ message: string | null; error: string | null }>({
    message: null,
    error: null
  });

  const wrapAction = useCallback(
    (fn: (scenarioId: string) => Promise<unknown>, successLabel: string) =>
      async (scenarioId: string) => {
        setOperationsStatus({ message: null, error: null });
        try {
          await fn(scenarioId);
          setOperationsStatus({ message: `${successLabel} (${scenarioId})`, error: null });
          await refresh();
        } catch (err) {
          const message = err instanceof Error ? err.message : 'operation failed';
          setOperationsStatus({ message: null, error: message });
          throw err;
        }
      },
    [refresh]
  );

  const handleReplay = useMemo(() => wrapAction(replayScenario, 'Replay triggered'), [wrapAction]);
  const handleRemediationTask = useMemo(
    () => wrapAction(openRemediationTask, 'Remediation task logged'),
    [wrapAction]
  );
  const handleRemediationPytest = useMemo(
    () => wrapAction(runRemediationPytest, 'Pytest subset dispatched'),
    [wrapAction]
  );

  if (loading) {
    return (
      <main>
        <section className="card">
          <p>Loading dashboard data…</p>
        </section>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main>
        <section className="card">
          <h2>Error</h2>
          <p>{error?.message ?? 'Unable to load dashboard data.'}</p>
        </section>
      </main>
    );
  }

  return (
    <main>
      <HeroSection
        playlistId={data.dashboard.latest_run?.playlist_id}
        runId={data.dashboard.latest_run?.run_id}
        updated={data.dashboard.last_updated}
      />
      <div className="dashboard-grid">
        <OverviewStats dashboard={data.dashboard} />
        <TinyllamaHealth snapshot={data.tinyllama_health} />
      </div>
      <div className="actions-grid">
        <ScenarioHighlights
          highlights={data.dashboard.scenario_highlights}
          onReplay={handleReplay}
          onOpenRemediation={handleRemediationTask}
          onRunPytest={handleRemediationPytest}
        />
        <OperationsPanel
          summary={data.operations}
          statusMessage={operationsStatus.message}
          statusError={operationsStatus.error}
        />
        <FlowchartMacroBuilder />
      </div>
      <HistoryPanel entries={data.history} />
    </main>
  );
}
