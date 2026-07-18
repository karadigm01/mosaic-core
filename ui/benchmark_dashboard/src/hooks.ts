import { useCallback, useEffect, useState } from 'react';
import { fetchDashboardState } from './api';
import type { DashboardStateResponse } from './types';

interface DashboardHookState {
  data: DashboardStateResponse | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useDashboardData(): DashboardHookState {
  const [data, setData] = useState<DashboardStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchState = useCallback(async () => {
    try {
      const payload = await fetchDashboardState();
      setData(payload);
      setError(null);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('unknown error'));
      setData(null);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchState();
    const interval = window.setInterval(() => {
      fetchState().catch(() => {
        /* errors handled inside fetchState */
      });
    }, 15000);

    return () => {
      window.clearInterval(interval);
    };
  }, [fetchState]);

  return { data, loading, error, refresh: fetchState };
}
