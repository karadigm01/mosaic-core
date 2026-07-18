import type { DashboardStateResponse } from './types';
export declare function fetchDashboardState(): Promise<DashboardStateResponse>;
export declare function replayScenario(scenarioId: string): Promise<unknown>;
export declare function openRemediationTask(scenarioId: string, reason?: string): Promise<unknown>;
export declare function runRemediationPytest(scenarioId: string): Promise<unknown>;
