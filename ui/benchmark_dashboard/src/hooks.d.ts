import type { DashboardStateResponse } from './types';
interface DashboardHookState {
    data: DashboardStateResponse | null;
    loading: boolean;
    error: Error | null;
    refresh: () => Promise<void>;
}
export declare function useDashboardData(): DashboardHookState;
export {};
