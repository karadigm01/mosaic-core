import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function OverviewStats({ dashboard }) {
    const aggregate = dashboard?.latest_run?.aggregate_metrics ?? {};
    const snapshot = dashboard?.coverage_snapshot ?? {};
    const stats = [
        { label: 'Scenarios', value: aggregate.scenario_count ?? snapshot.scenario_count ?? 0 },
        { label: 'Failures', value: aggregate.failures ?? 0 },
        { label: 'Pytest Targets', value: snapshot.pytest_targets?.length ?? 0 },
        { label: 'Latency Span (ms)', value: snapshot.tinyllama_latency_span_ms ?? '—' }
    ];
    return (_jsxs("section", { className: "card", children: [_jsx("h2", { children: "Aggregate Metrics" }), _jsx("div", { className: "stats-grid", children: stats.map((stat) => (_jsxs("div", { className: "stat", children: [_jsx("div", { className: "stat-label", children: stat.label }), _jsx("div", { className: "stat-value", children: stat.value })] }, stat.label))) })] }));
}
