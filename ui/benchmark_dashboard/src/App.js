import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback, useMemo } from 'react';
import { useDashboardData } from './hooks';
import { OverviewStats } from './components/OverviewStats';
import { ScenarioHighlights } from './components/ScenarioHighlights';
import { HistoryPanel } from './components/HistoryPanel';
import { TinyllamaHealth } from './components/TinyllamaHealth';
import { OperationsPanel } from './components/OperationsPanel';
import { replayScenario, openRemediationTask, runRemediationPytest } from './api';
function HeroSection({ playlistId, runId, updated }) {
    return (_jsxs("section", { className: "card hero", children: [_jsxs("div", { children: [_jsx("h1", { children: "Benchmark Observatory" }), _jsx("p", { children: "Live view of playlist telemetry, resolver coverage, and TinyLLaMA health. Consume the JSON-first evidence without spelunking logs." }), _jsxs("div", { className: "chip-row", children: [_jsxs("span", { className: "chip", children: ["Playlist: ", playlistId ?? 'n/a'] }), _jsxs("span", { className: "chip", children: ["Run: ", runId ?? 'n/a'] }), _jsxs("span", { className: "chip", children: ["Updated: ", updated ?? '—'] })] })] }), _jsxs("div", { className: "button-row", children: [_jsx("button", { onClick: () => window.location.reload(), children: "Refresh" }), _jsx("button", { className: "secondary", onClick: () => window.open('/api/dashboard', '_blank')?.focus(), children: "View JSON" })] })] }));
}
export default function App() {
    const { data, loading, error, refresh } = useDashboardData();
    const [operationsStatus, setOperationsStatus] = useState({
        message: null,
        error: null
    });
    const wrapAction = useCallback((fn, successLabel) => async (scenarioId) => {
        setOperationsStatus({ message: null, error: null });
        try {
            await fn(scenarioId);
            setOperationsStatus({ message: `${successLabel} (${scenarioId})`, error: null });
            await refresh();
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'operation failed';
            setOperationsStatus({ message: null, error: message });
            throw err;
        }
    }, [refresh]);
    const handleReplay = useMemo(() => wrapAction(replayScenario, 'Replay triggered'), [wrapAction]);
    const handleRemediationTask = useMemo(() => wrapAction(openRemediationTask, 'Remediation task logged'), [wrapAction]);
    const handleRemediationPytest = useMemo(() => wrapAction(runRemediationPytest, 'Pytest subset dispatched'), [wrapAction]);
    if (loading) {
        return (_jsx("main", { children: _jsx("section", { className: "card", children: _jsx("p", { children: "Loading dashboard data\u2026" }) }) }));
    }
    if (error || !data) {
        return (_jsx("main", { children: _jsxs("section", { className: "card", children: [_jsx("h2", { children: "Error" }), _jsx("p", { children: error?.message ?? 'Unable to load dashboard data.' })] }) }));
    }
    return (_jsxs("main", { children: [_jsx(HeroSection, { playlistId: data.dashboard.latest_run?.playlist_id, runId: data.dashboard.latest_run?.run_id, updated: data.dashboard.last_updated }), _jsxs("div", { className: "dashboard-grid", children: [_jsx(OverviewStats, { dashboard: data.dashboard }), _jsx(TinyllamaHealth, { snapshot: data.tinyllama_health })] }), _jsxs("div", { className: "actions-grid", children: [_jsx(ScenarioHighlights, { highlights: data.dashboard.scenario_highlights, onReplay: handleReplay, onOpenRemediation: handleRemediationTask, onRunPytest: handleRemediationPytest }), _jsx(OperationsPanel, { summary: data.operations, statusMessage: operationsStatus.message, statusError: operationsStatus.error })] }), _jsx(HistoryPanel, { entries: data.history })] }));
}
