import type { ScenarioHighlight } from '../types';
interface ScenarioHighlightsProps {
    highlights?: ScenarioHighlight[];
    onReplay?: (scenarioId: string) => Promise<void>;
    onOpenRemediation?: (scenarioId: string) => Promise<void>;
    onRunPytest?: (scenarioId: string) => Promise<void>;
}
export declare function ScenarioHighlights({ highlights, onReplay, onOpenRemediation, onRunPytest }: ScenarioHighlightsProps): import("react/jsx-runtime").JSX.Element;
export {};
