import type { OperationsSummary } from '../types';
interface OperationsPanelProps {
    summary?: OperationsSummary;
    statusMessage?: string | null;
    statusError?: string | null;
}
export declare function OperationsPanel({ summary, statusMessage, statusError }: OperationsPanelProps): import("react/jsx-runtime").JSX.Element;
export {};
