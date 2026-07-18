import type { DashboardPayload } from '../types';

interface OverviewStatsProps {
  dashboard?: DashboardPayload | null;
}

export function OverviewStats({ dashboard }: OverviewStatsProps) {
  const aggregate = dashboard?.latest_run?.aggregate_metrics ?? {};
  const snapshot = dashboard?.coverage_snapshot ?? {};

  const stats = [
    { label: 'Scenarios', value: aggregate.scenario_count ?? snapshot.scenario_count ?? 0 },
    { label: 'Failures', value: aggregate.failures ?? 0 },
    { label: 'Pytest Targets', value: snapshot.pytest_targets?.length ?? 0 },
    { label: 'Latency Span (ms)', value: snapshot.tinyllama_latency_span_ms ?? '—' }
  ];

  return (
    <section className="card">
      <h2>Aggregate Metrics</h2>
      <div className="stats-grid">
        {stats.map((stat) => (
          <div className="stat" key={stat.label}>
            <div className="stat-label">{stat.label}</div>
            <div className="stat-value">{stat.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
