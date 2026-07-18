import { useState } from 'react';
import type { ScenarioHighlight } from '../types';

interface ScenarioHighlightsProps {
  highlights?: ScenarioHighlight[];
  onReplay?: (scenarioId: string) => Promise<void>;
  onOpenRemediation?: (scenarioId: string) => Promise<void>;
  onRunPytest?: (scenarioId: string) => Promise<void>;
}

const statusClass = (status?: string) => {
  if (!status) return 'chip';
  return `chip ${status.toLowerCase()}`;
};

type ActionType = 'replay' | 'task' | 'pytest';

export function ScenarioHighlights({
  highlights,
  onReplay,
  onOpenRemediation,
  onRunPytest
}: ScenarioHighlightsProps) {
  const [pending, setPending] = useState<Record<string, ActionType | null>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const runAction = async (
    scenarioId: string,
    type: ActionType,
    action?: (scenarioId: string) => Promise<void>
  ) => {
    if (!action) return;
    setPending((prev) => ({ ...prev, [scenarioId]: type }));
    setErrors((prev) => ({ ...prev, [scenarioId]: '' }));
    setMessages((prev) => ({ ...prev, [scenarioId]: '' }));
    try {
      await action(scenarioId);
      setMessages((prev) => ({ ...prev, [scenarioId]: `${type} complete` }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'operation failed';
      setErrors((prev) => ({ ...prev, [scenarioId]: message }));
    } finally {
      setPending((prev) => ({ ...prev, [scenarioId]: null }));
    }
  };

  if (!highlights || highlights.length === 0) {
    return (
      <section className="card">
        <h2>Scenario Highlights</h2>
        <p>No scenario data available.</p>
      </section>
    );
  }
  return (
    <section className="card">
      <h2>Scenario Highlights</h2>
      <div className="timeline">
        {highlights.map((highlight) => (
          <div className="timeline-entry" key={highlight.scenario_id}>
            <strong>{highlight.scenario_id}</strong>
            <div className="chip-row">
              <span className={statusClass(highlight.coverage?.status)}>
                {highlight.coverage?.status ?? 'unknown'}
              </span>
              {typeof highlight.tinyllama_latency_ms === 'number' && (
                <span className="chip">{highlight.tinyllama_latency_ms} ms</span>
              )}
              {typeof highlight.return_code === 'number' && (
                <span className="chip">return {highlight.return_code}</span>
              )}
            </div>
            <div className="button-row">
              <button
                onClick={() => runAction(highlight.scenario_id, 'replay', onReplay)}
                disabled={pending[highlight.scenario_id] === 'replay'}
              >
                {pending[highlight.scenario_id] === 'replay' ? 'Replaying…' : 'Replay Scenario'}
              </button>
              <button
                className="secondary"
                onClick={() => runAction(highlight.scenario_id, 'task', onOpenRemediation)}
                disabled={pending[highlight.scenario_id] === 'task'}
              >
                {pending[highlight.scenario_id] === 'task' ? 'Logging…' : 'Log Remediation'}
              </button>
              <button
                className="secondary"
                onClick={() => runAction(highlight.scenario_id, 'pytest', onRunPytest)}
                disabled={pending[highlight.scenario_id] === 'pytest'}
              >
                {pending[highlight.scenario_id] === 'pytest' ? 'Running…' : 'Pytest Subset'}
              </button>
            </div>
            {(messages[highlight.scenario_id] || errors[highlight.scenario_id]) && (
              <p className={`status-text ${errors[highlight.scenario_id] ? 'error' : 'success'}`}>
                {errors[highlight.scenario_id] || messages[highlight.scenario_id]}
              </p>
            )}
            {highlight.presentation?.view_counts && (
              <p>
                Views:{' '}
                {Object.entries(highlight.presentation.view_counts)
                  .map(([name, value]) => `${name}:${value}`)
                  .join(', ')}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
