import type { DashboardStateResponse, MacroCatalogResponse, MacroTileRequest, MacroTileResponse } from './types';

const DEFAULT_ENDPOINT = '/api/dashboard';

export async function fetchDashboardState(): Promise<DashboardStateResponse> {
  const response = await fetch(DEFAULT_ENDPOINT);
  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard state: ${response.status}`);
  }
  return response.json();
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
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

export function replayScenario(scenarioId: string) {
  return postJson('/api/replay', { scenario_id: scenarioId });
}

export function openRemediationTask(scenarioId: string, reason?: string) {
  return postJson('/api/remediation', { scenario_id: scenarioId, action: 'open_task', reason });
}

export function runRemediationPytest(scenarioId: string) {
  return postJson('/api/remediation', { scenario_id: scenarioId, action: 'pytest_subset' });
}

export async function fetchMacroCatalog(): Promise<MacroCatalogResponse> {
  const response = await fetch('/api/macro_tiles/catalog');
  if (!response.ok) {
    throw new Error(`Failed to load macro tile catalog: ${response.status}`);
  }
  return response.json();
}

export function generateMacroTile(payload: MacroTileRequest) {
  return postJson<MacroTileResponse>('/api/macro_tiles', payload);
}
