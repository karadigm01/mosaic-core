import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function HistoryPanel({ entries }) {
    const safeEntries = entries ?? [];
    return (_jsxs("section", { className: "card", children: [_jsx("h2", { children: "Playlist History" }), _jsxs("div", { className: "timeline", children: [safeEntries.length === 0 && _jsx("p", { children: "No history snapshots captured yet." }), safeEntries.map((entry) => (_jsxs("div", { className: "timeline-entry", children: [_jsx("strong", { children: entry.playlist_id ?? 'Unknown playlist' }), _jsxs("div", { className: "chip-row", children: [_jsx("span", { className: "chip", children: entry.run_id }), _jsxs("span", { className: "chip", children: [entry.scenario_count ?? 0, " scenarios"] })] }), _jsx("small", { children: entry.last_updated ?? 'timestamp unavailable' }), entry.coverage_status && (_jsxs("p", { children: ["Coverage:", ' ', Object.entries(entry.coverage_status)
                                        .map(([status, count]) => `${status}:${count}`)
                                        .join(', ')] })), _jsx("p", { className: "text-muted", children: entry.path })] }, entry.path)))] })] }));
}
