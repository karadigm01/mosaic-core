import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
const statusClass = (status) => {
    if (!status)
        return 'chip';
    return `chip ${status.toLowerCase()}`;
};
export function ScenarioHighlights({ highlights, onReplay, onOpenRemediation, onRunPytest }) {
    const [pending, setPending] = useState({});
    const [messages, setMessages] = useState({});
    const [errors, setErrors] = useState({});
    const runAction = async (scenarioId, type, action) => {
        if (!action)
            return;
        setPending((prev) => ({ ...prev, [scenarioId]: type }));
        setErrors((prev) => ({ ...prev, [scenarioId]: '' }));
        setMessages((prev) => ({ ...prev, [scenarioId]: '' }));
        try {
            await action(scenarioId);
            setMessages((prev) => ({ ...prev, [scenarioId]: `${type} complete` }));
        }
        catch (error) {
            const message = error instanceof Error ? error.message : 'operation failed';
            setErrors((prev) => ({ ...prev, [scenarioId]: message }));
        }
        finally {
            setPending((prev) => ({ ...prev, [scenarioId]: null }));
        }
    };
    if (!highlights || highlights.length === 0) {
        return (_jsxs("section", { className: "card", children: [_jsx("h2", { children: "Scenario Highlights" }), _jsx("p", { children: "No scenario data available." })] }));
    }
    return (_jsxs("section", { className: "card", children: [_jsx("h2", { children: "Scenario Highlights" }), _jsx("div", { className: "timeline", children: highlights.map((highlight) => (_jsxs("div", { className: "timeline-entry", children: [_jsx("strong", { children: highlight.scenario_id }), _jsxs("div", { className: "chip-row", children: [_jsx("span", { className: statusClass(highlight.coverage?.status), children: highlight.coverage?.status ?? 'unknown' }), typeof highlight.tinyllama_latency_ms === 'number' && (_jsxs("span", { className: "chip", children: [highlight.tinyllama_latency_ms, " ms"] })), typeof highlight.return_code === 'number' && (_jsxs("span", { className: "chip", children: ["return ", highlight.return_code] }))] }), _jsxs("div", { className: "button-row", children: [_jsx("button", { onClick: () => runAction(highlight.scenario_id, 'replay', onReplay), disabled: pending[highlight.scenario_id] === 'replay', children: pending[highlight.scenario_id] === 'replay' ? 'Replaying…' : 'Replay Scenario' }), _jsx("button", { className: "secondary", onClick: () => runAction(highlight.scenario_id, 'task', onOpenRemediation), disabled: pending[highlight.scenario_id] === 'task', children: pending[highlight.scenario_id] === 'task' ? 'Logging…' : 'Log Remediation' }), _jsx("button", { className: "secondary", onClick: () => runAction(highlight.scenario_id, 'pytest', onRunPytest), disabled: pending[highlight.scenario_id] === 'pytest', children: pending[highlight.scenario_id] === 'pytest' ? 'Running…' : 'Pytest Subset' })] }), (messages[highlight.scenario_id] || errors[highlight.scenario_id]) && (_jsx("p", { className: `status-text ${errors[highlight.scenario_id] ? 'error' : 'success'}`, children: errors[highlight.scenario_id] || messages[highlight.scenario_id] })), highlight.presentation?.view_counts && (_jsxs("p", { children: ["Views:", ' ', Object.entries(highlight.presentation.view_counts)
                                    .map(([name, value]) => `${name}:${value}`)
                                    .join(', ')] }))] }, highlight.scenario_id))) })] }));
}
