import { useEffect, useMemo, useState } from 'react';
import { fetchMacroCatalog, generateMacroTile } from '../api';
import type { MacroCatalogTile, MacroLifecycleState, MacroTileResponse } from '../types';

const lifecycleOptions: MacroLifecycleState[] = ['proposed', 'sandboxed', 'promoted'];

function formatLifecycle(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function FlowchartMacroBuilder() {
  const [catalog, setCatalog] = useState<MacroCatalogTile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTiles, setSelectedTiles] = useState<string[]>([]);
  const [tileId, setTileId] = useState('tile.macro.');
  const [tileName, setTileName] = useState('');
  const [lifecycleState, setLifecycleState] = useState<MacroLifecycleState>('proposed');
  const [registerComponent, setRegisterComponent] = useState(false);
  const [status, setStatus] = useState<{ message?: string; error?: string; response?: MacroTileResponse }>({});

  useEffect(() => {
    fetchMacroCatalog()
      .then((payload) => {
        setCatalog(payload.tiles ?? []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Unable to load catalog');
        setLoading(false);
      });
  }, []);

  const promotedTiles = useMemo(
    () => catalog.filter((tile) => (tile.lifecycle_state ?? '').toLowerCase() === 'promoted'),
    [catalog]
  );

  const planValid = tileId.trim().length > 0 && tileName.trim().length > 0 && selectedTiles.length >= 2;
  const canRegister = lifecycleState === 'promoted';

  const addTileToPlan = (tileIdToAdd: string) => {
    setSelectedTiles((prev) => (prev.includes(tileIdToAdd) ? prev : [...prev, tileIdToAdd]));
  };

  const removeTileFromPlan = (tileIdToRemove: string) => {
    setSelectedTiles((prev) => prev.filter((id) => id !== tileIdToRemove));
  };

  const clearPlan = () => {
    setSelectedTiles([]);
  };

  const handleGenerate = async () => {
    if (!planValid) {
      return;
    }
    setStatus({ message: 'Synthesizing macro tile…' });
    try {
      const response = await generateMacroTile({
        tile_id: tileId.trim(),
        tile_name: tileName.trim(),
        plan: selectedTiles,
        lifecycle_state: lifecycleState,
        register_component: registerComponent && canRegister,
      });
      setStatus({
        message: `Generated macro tile ${tileId.trim()} (${response.component_registered ? 'registered' : 'pending'})`,
        response,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'macro tile generation failed';
      setStatus({ error: message });
    }
  };

  return (
    <section className="card macro-card">
      <div className="macro-card-header">
        <h2>Flowchart Macro Builder</h2>
        <p className="text-muted">
          Compose promoted tiles into a flowchart plan, call the resolver-backed generator, and capture the artifact paths
          without leaving the dashboard.
        </p>
      </div>
      {loading && <p>Loading promoted tiles…</p>}
      {error && !loading && <p className="status-text error">{error}</p>}
      {!loading && !error && (
        <div className="flowchart-builder">
          <div className="tile-palette">
            <h3>Promoted Tiles</h3>
            <div className="tile-list">
              {promotedTiles.map((tile) => (
                <button
                  key={tile.tile_id}
                  type="button"
                  className={`tile-node ${selectedTiles.includes(tile.tile_id) ? 'selected' : ''}`}
                  onClick={() => addTileToPlan(tile.tile_id)}
                >
                  <span>{tile.tile_name}</span>
                  <small>{tile.capability ?? tile.tile_id}</small>
                </button>
              ))}
              {promotedTiles.length === 0 && <p className="text-muted">No promoted tiles available.</p>}
            </div>
          </div>
          <div className="plan-pipeline">
            <h3>Capability Plan</h3>
            {selectedTiles.length === 0 ? (
              <p className="text-muted">Select at least two tiles to form the resolver capability chain.</p>
            ) : (
              <div className="plan-sequence">
                {selectedTiles.map((tile, index) => (
                  <div key={tile} className="plan-node">
                    <span>{tile}</span>
                    <button type="button" onClick={() => removeTileFromPlan(tile)}>
                      Remove
                    </button>
                    {index < selectedTiles.length - 1 && <span className="plan-arrow">→</span>}
                  </div>
                ))}
              </div>
            )}
            {selectedTiles.length > 0 && (
              <button className="text-button" type="button" onClick={clearPlan}>
                Clear plan
              </button>
            )}
          </div>
          <div className="macro-form">
            <label>
              Tile ID
              <input value={tileId} onChange={(event) => setTileId(event.target.value)} placeholder="tile.macro.chain" />
            </label>
            <label>
              Tile Name
              <input value={tileName} onChange={(event) => setTileName(event.target.value)} placeholder="Flowchart Macro Tile" />
            </label>
            <label>
              Lifecycle State
              <select
                value={lifecycleState}
                onChange={(event) => {
                  const nextState = event.target.value as MacroLifecycleState;
                  setLifecycleState(nextState);
                  if (nextState !== 'promoted') {
                    setRegisterComponent(false);
                  }
                }}
              >
                {lifecycleOptions.map((option) => (
                  <option key={option} value={option}>
                    {formatLifecycle(option)}
                  </option>
                ))}
              </select>
            </label>
            <label className={`checkbox-row ${!canRegister ? 'disabled' : ''}`}>
              <input
                type="checkbox"
                checked={registerComponent && canRegister}
                onChange={(event) => setRegisterComponent(event.target.checked)}
                disabled={!canRegister}
              />
              Auto-register in component index (requires promoted)
            </label>
            <button type="button" onClick={handleGenerate} disabled={!planValid}>
              Generate Macro Tile
            </button>
            {!planValid && <p className="text-muted">Provide an ID, name, and select at least two tiles.</p>}
            {status.message && <p className="status-text success">{status.message}</p>}
            {status.error && <p className="status-text error">{status.error}</p>}
            {status.response && (
              <div className="artifact-list">
                <h4>Latest Artifacts</h4>
                <ul>
                  {Object.entries(status.response.artifacts).map(([label, path]) => (
                    <li key={label}>
                      <span>{label}</span>
                      <code>{path}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
