interface TinyllamaHealthProps {
    snapshot?: {
        status_code?: number;
        latency_ms?: number;
        failure_reason?: string | null;
    };
}
export declare function TinyllamaHealth({ snapshot }: TinyllamaHealthProps): import("react/jsx-runtime").JSX.Element;
export {};
