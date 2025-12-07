import { useEffect, useMemo, useState } from "react";

type TraceEvent = {
  trace_id: string;
  timestamp: number;
  node: string;
  status: string;
  message: string;
  extra: {
    duration_ms?: number;
    [k: string]: any;
  };
};

type SlowNode = {
  node: string;
  total_ms: number;
  count: number;
  avg: number;
};

type TraceResponse = {
  events: TraceEvent[];
  summary: {
    total_events: number;
    per_node: Record<string, number>;
    failures: number;
  };
  slowest?: SlowNode[];
};

type TraceGroup = {
  id: string;
  events: TraceEvent[];
};

export default function TraceInspectorApp() {
  const [data, setData] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  // filters / controls
  const [live, setLive] = useState(false);
  const [traceSearch, setTraceSearch] = useState("");
  const [nodeFilter, setNodeFilter] = useState("");
  const [minMs, setMinMs] = useState(0);
  const [showFailedOnly, setShowFailedOnly] = useState(false);
  const [slowLimit, setSlowLimit] = useState(300);
  const [criticalLimit, setCriticalLimit] = useState(800);

  // -------- data loading --------

  const load = () => {
    fetch("http://127.0.0.1:8000/v1/assistant/debug/trace")
      .then((res) => res.json())
      .then((json) => {
        setData(json as TraceResponse);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load trace:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [live]);

  // ----- derived data -----

  const events = data?.events ?? [];

  const nodes = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(e.node);
    return Array.from(s).sort();
  }, [events]);

  const traces: TraceGroup[] = useMemo(() => {
    const byId = new Map<string, TraceEvent[]>();
    for (const e of events) {
      if (!byId.has(e.trace_id)) byId.set(e.trace_id, []);
      byId.get(e.trace_id)!.push(e);
    }
    for (const list of byId.values()) {
      list.sort((a, b) => a.timestamp - b.timestamp);
    }
    return Array.from(byId.entries()).map(([id, evs]) => ({ id, events: evs }));
  }, [events]);

  const slowestNodes: SlowNode[] = (data?.slowest as any) ?? [];

  // ----- filtering -----

  const filteredTraces: TraceGroup[] = useMemo(() => {
    return traces.filter((t) => {
      if (traceSearch && !t.id.includes(traceSearch)) return false;

      if (nodeFilter) {
        const matchNode = t.events.some((e) =>
          e.node.toLowerCase().includes(nodeFilter.toLowerCase())
        );
        if (!matchNode) return false;
      }

      if (showFailedOnly) {
        const hasFail = t.events.some(
          (e) => e.status === "FAILED" || e.status === "ERROR"
        );
        if (!hasFail) return false;
      }

      if (minMs > 0) {
        const hasSlow = t.events.some(
          (e) => (e.extra?.duration_ms ?? 0) >= minMs
        );
        if (!hasSlow) return false;
      }

      return true;
    });
  }, [traces, traceSearch, nodeFilter, showFailedOnly, minMs]);

  const visibleTraces = filteredTraces.length > 0 ? filteredTraces : traces;

  const selectedTrace: TraceGroup | undefined =
    selectedTraceId != null
      ? visibleTraces.find((t) => t.id === selectedTraceId)
      : visibleTraces[visibleTraces.length - 1]; // default → most recent visible

  // Heatmap color helper
  function cellColor(ev: TraceEvent | undefined): string {
    if (!ev) return "transparent";
    const dur = ev.extra?.duration_ms ?? 0;

    // Failed overrides
    if (ev.status === "FAILED" || ev.status === "ERROR") {
      return "#8b1e3f"; // dark red
    }

    if (dur === 0) return "#222"; // unknown duration

    if (dur >= criticalLimit) return "#e53935"; // very slow — red
    if (dur >= slowLimit) return "#f9a825"; // slow — yellow
    if (dur < slowLimit && dur > 0) return "#1b5e20"; // fast — green

    return "#33691e";
  }

  function formatMs(ms?: number) {
    if (!ms && ms !== 0) return "";
    if (ms < 1000) return `${ms.toFixed(0)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
  }

  if (loading) {
    return (
      <div style={pageStyle}>
        <h3>Loading Trace...</h3>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={pageStyle}>
        <h3>Failed to load trace data.</h3>
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      <header style={headerStyle}>
        <div>
          <h1 style={{ margin: 0 }}>🧠 Cypher Trace Heatmap</h1>
          <p style={{ margin: "4px 0", opacity: 0.75 }}>
            Phase-4 · Multi-agent orchestration · Live execution traces
          </p>
        </div>
        <button
          onClick={load}
          style={refreshButtonStyle}
        >
          ⟳ Refresh
        </button>
      </header>

      {/* Controls row */}
      <div style={controlsRowStyle}>
        <label style={controlItemStyle}>
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => setLive(e.target.checked)}
          />{" "}
          Live
        </label>

        <label style={controlItemStyle}>
          Trace ID
          <input
            style={controlInputStyle}
            value={traceSearch}
            onChange={(e) => setTraceSearch(e.target.value)}
            placeholder="search trace id"
          />
        </label>

        <label style={controlItemStyle}>
          Node
          <input
            style={controlInputStyle}
            value={nodeFilter}
            onChange={(e) => setNodeFilter(e.target.value)}
            placeholder="entity / planner / chat..."
          />
        </label>

        <label style={controlItemStyle}>
          Min duration (ms)
          <input
            type="number"
            style={controlInputStyle}
            value={minMs}
            onChange={(e) => setMinMs(Number(e.target.value) || 0)}
          />
        </label>

        <label style={controlItemStyle}>
          Slow ≥ (ms)
          <input
            type="number"
            style={controlInputStyle}
            value={slowLimit}
            onChange={(e) => setSlowLimit(Number(e.target.value) || 0)}
          />
        </label>

        <label style={controlItemStyle}>
          Critical ≥ (ms)
          <input
            type="number"
            style={controlInputStyle}
            value={criticalLimit}
            onChange={(e) => setCriticalLimit(Number(e.target.value) || 0)}
          />
        </label>

        <label style={controlItemStyle}>
          <input
            type="checkbox"
            checked={showFailedOnly}
            onChange={(e) => setShowFailedOnly(e.target.checked)}
          />{" "}
          Failed only
        </label>
      </div>

      {/* Top row: summary + slowest */}
      <div style={topRowStyle}>
        <section style={cardStyle}>
          <h2>Summary</h2>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <SummaryStat
              label="Total events"
              value={data.summary.total_events}
            />
            <SummaryStat
              label="Nodes"
              value={Object.keys(data.summary.per_node).length}
            />
            <SummaryStat label="Failures" value={data.summary.failures} />
          </div>
          <h4 style={{ marginTop: 16 }}>Events per node</h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {Object.entries(data.summary.per_node).map(([node, count]) => (
              <li key={node}>
                <code>{node}</code>: {count}
              </li>
            ))}
          </ul>
        </section>

        <section style={cardStyle}>
          <h2>Slowest Nodes</h2>
          {slowestNodes.length === 0 ? (
            <p style={{ opacity: 0.7 }}>No duration data yet.</p>
          ) : (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Total</th>
                  <th>Calls</th>
                  <th>Avg</th>
                </tr>
              </thead>
              <tbody>
                {slowestNodes.map((s) => (
                  <tr key={s.node}>
                    <td>
                      <code>{s.node}</code>
                    </td>
                    <td>{formatMs(s.total_ms)}</td>
                    <td>{s.count}</td>
                    <td>{formatMs(s.avg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {/* Heatmap + details */}
      <div style={bottomRowStyle}>
        <section style={{ ...cardStyle, flex: 2 }}>
          <h2>Execution Heatmap</h2>
          {visibleTraces.length === 0 ? (
            <p style={{ opacity: 0.7 }}>No traces recorded yet.</p>
          ) : (
            <>
              <div style={heatmapLegendStyle}>
                <span>Fast</span>
                <span
                  style={{ background: "#1b5e20", width: 40, height: 10 }}
                />
                <span
                  style={{ background: "#f9a825", width: 40, height: 10 }}
                />
                <span
                  style={{ background: "#e53935", width: 40, height: 10 }}
                />
                <span>Slow</span>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ ...tableStyle, fontSize: 12, minWidth: 600 }}>
                  <thead>
                    <tr>
                      <th>Trace</th>
                      {nodes.map((n) => (
                        <th key={n}>
                          <code>{n}</code>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleTraces.map((t) => {
                      const hasFail = t.events.some(
                        (e) =>
                          e.status === "FAILED" || e.status === "ERROR"
                      );
                      return (
                        <tr
                          key={t.id}
                          onClick={() => setSelectedTraceId(t.id)}
                          style={{
                            cursor: "pointer",
                            backgroundColor:
                              selectedTrace?.id === t.id
                                ? "#252a39"
                                : hasFail
                                ? "#2b0e1a"
                                : "transparent",
                          }}
                        >
                          <td>
                            <code>{t.id.slice(0, 8)}</code>
                          </td>
                          {nodes.map((node) => {
                            const ev = t.events.find((e) => e.node === node);
                            const dur = ev?.extra?.duration_ms;
                            return (
                              <td key={node}>
                                <div
                                  title={
                                    ev
                                      ? `${node}\n${ev.status}\n${formatMs(
                                          dur
                                        )}\n${ev.message || ""}`
                                      : `${node}\n(no event)`
                                  }
                                  style={{
                                    width: "100%",
                                    height: 18,
                                    borderRadius: 4,
                                    background: cellColor(ev),
                                    border: "1px solid #333",
                                  }}
                                />
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section style={{ ...cardStyle, flex: 1 }}>
          <h2>Trace Details</h2>
          {!selectedTrace ? (
            <p style={{ opacity: 0.7 }}>Select a trace row to inspect it.</p>
          ) : (
            <>
              <p style={{ fontSize: 12, opacity: 0.8 }}>
                <strong>Trace ID:</strong> <code>{selectedTrace.id}</code>
              </p>
              <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                {selectedTrace.events.map((e) => (
                  <li key={`${e.node}-${e.timestamp}`}>
                    <div>
                      <code>{e.node}</code> — {e.status} —{" "}
                      {formatMs(e.extra?.duration_ms)}
                    </div>
                    {e.message && (
                      <div style={{ opacity: 0.75 }}>{e.message}</div>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

// ----- small presentational helpers -----

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        padding: 10,
        borderRadius: 8,
        background: "#151827",
        minWidth: 100,
      }}
    >
      <div style={{ fontSize: 12, opacity: 0.7 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  minHeight: "100vh",
  background: "#050712",
  color: "#e5e7eb",
  padding: 20,
  fontFamily:
    "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 8,
};

const controlsRowStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 12,
  alignItems: "center",
  marginBottom: 16,
};

const controlItemStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 12,
};

const controlInputStyle: React.CSSProperties = {
  padding: "4px 6px",
  borderRadius: 6,
  border: "1px solid #374151",
  background: "#020617",
  color: "#e5e7eb",
  fontSize: 12,
};

const topRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 16,
  flexWrap: "wrap",
};

const bottomRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 16,
  marginTop: 16,
  flexWrap: "wrap",
};

const cardStyle: React.CSSProperties = {
  background: "#0b0f1d",
  borderRadius: 12,
  padding: 16,
  boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
  border: "1px solid #111827",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
};

const refreshButtonStyle: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 999,
  border: "1px solid #4b5563",
  background: "#111827",
  color: "#e5e7eb",
  cursor: "pointer",
  fontSize: 13,
};

const heatmapLegendStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 11,
  opacity: 0.8,
  marginBottom: 8,
};
