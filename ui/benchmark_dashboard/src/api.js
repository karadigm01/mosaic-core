const DEFAULT_ENDPOINT = '/api/dashboard';
export async function fetchDashboardState() {
    const response = await fetch(DEFAULT_ENDPOINT);
    if (!response.ok) {
        throw new Error(`Failed to fetch dashboard state: ${response.status}`);
    }
    return response.json();
}
async function postJson(url, body) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`Request failed (${response.status}): ${text}`);
    }
    return response.json();
}
export function replayScenario(scenarioId) {
    return postJson('/api/replay', { scenario_id: scenarioId });
}
export function openRemediationTask(scenarioId, reason) {
    return postJson('/api/remediation', { scenario_id: scenarioId, action: 'open_task', reason });
}
export function runRemediationPytest(scenarioId) {
    return postJson('/api/remediation', { scenario_id: scenarioId, action: 'pytest_subset' });
}
