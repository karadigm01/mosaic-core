export interface ScenarioHighlight {
  scenario_id: string;
  tinyllama_latency_ms?: number;
  return_code?: number;
  coverage?: {
    status?: string;
    requirements?: Record<string, boolean>;
  };
  presentation?: {
    view_counts?: Record<string, number>;
    pressure_state?: Record<string, unknown>;
  };
}

export interface DashboardPayload {
  last_updated?: string;
  latest_run?: {
    playlist_id?: string;
    run_id?: string;
    aggregate_metrics?: Record<string, number>;
  };
  coverage_snapshot?: {
    scenario_count?: number;
    failing_scenarios?: unknown[];
    pytest_targets?: unknown[];
    tinyllama_latency_span_ms?: number;
  };
  scenario_highlights?: ScenarioHighlight[];
}

export interface HistoryEntrySummary {
  path: string;
  last_updated?: string;
  playlist_id?: string;
  run_id?: string;
  scenario_count?: number;
  coverage_status?: Record<string, number>;
}

export interface DashboardStateResponse {
  dashboard: DashboardPayload;
  history: HistoryEntrySummary[];
  tinyllama_health?: {
    status_code?: number;
    latency_ms?: number;
    failure_reason?: string | null;
  };
  operations?: OperationsSummary;
  source_paths: {
    dashboard: string;
    history_dir: string;
    kb_index: string;
  };
}

export interface ReplayEvent {
  id: string;
  timestamp: string;
  scenario_id: string;
  run_id?: string;
  artifact_path?: string;
  return_code?: number;
}

export interface RemediationEvent {
  id: string;
  timestamp: string;
  scenario_id: string;
  action: string;
  status: string;
  details?: Record<string, unknown>;
}

export interface OperationsSummary {
  replay_count: number;
  remediation_backlog: number;
  remediation_total?: number;
  last_replay_timestamp?: string | null;
  recent_replays?: ReplayEvent[];
  recent_remediations?: RemediationEvent[];
}

export type MacroLifecycleState = 'proposed' | 'sandboxed' | 'promoted';

export interface MacroCatalogTile {
  tile_id: string;
  tile_name: string;
  capability?: string | null;
  lifecycle_state?: MacroLifecycleState | string;
  inputs?: string[];
  outputs?: string[];
}

export interface MacroCatalogResponse {
  tiles: MacroCatalogTile[];
}

export interface MacroTileRequest {
  tile_id: string;
  tile_name: string;
  plan: string[];
  generated_by?: string;
  lifecycle_state?: MacroLifecycleState;
  register_component?: boolean;
  timestamp?: string;
}

export interface MacroTileResponse {
  status: string;
  artifacts: Record<string, string>;
  lifecycle_state: MacroLifecycleState | string;
  component_registered: boolean;
  component_index_path?: string;
}
