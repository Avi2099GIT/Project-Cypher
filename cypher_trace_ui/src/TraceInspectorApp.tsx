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

export default function TraceInspectorApp() {
  const [data, setData] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  useEffect(() => {
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
  }, []);

  // ----- derived data -----

  const events = data?.events ?? [];

  const nodes = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(e.node);
    return Array.from(s).sort();
  }, [events]);

  const traces = useMemo(() => {
    const byId = new Map<string, TraceEvent[]>();
    for (const e of events) {
      if (!byId.has(e.trace_id)) byId.set(e.trace_id, []);
      byId.get(e.trace_id)!.push(e);
    }
    // Sort events within each trace by time
    for (const list of byId.values()) {
      list.sort((a, b) => a.timestamp - b.timestamp);
    }
    // Convert to array of { id, events }
    return Array.from(byId.entries()).map(([id, evs]) => ({ id, events: evs }));
  }, [events]);

  const slowestNodes: SlowNode[] = (data?.slowest as any) ?? [];

  const selectedTrace =
    selectedTraceId != null
      ? traces.find((t) => t.id === selectedTraceId)
      : traces[traces.length - 1]; // default → most recent

  // Heatmap color helper
  function cellColor(ev: TraceEvent | undefined): string {
    if (!ev) return "transparent";
    const dur = ev.extra?.duration_ms ?? 0;

    // Failed overrides
    if (ev.status === "FAILED" || ev.status === "ERROR") {
      return "#8b1e3f"; // dark red
    }

    if (dur === 0) return "#222"; // unknown duration

    if (dur < 80) return "#1b5e20"; // fast — dark green
    if (dur < 250) return "#33691e"; // ok
    if (dur < 750) return "#f9a825"; // slow — yellow
    return "#e53935"; // very slow — red
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
          onClick={() => {
            setLoading(true);
            fetch("http://127.0.0.1:8000/v1/assistant/debug/trace")
              .then((res) => res.json())
              .then((json) => {
                setData(json as TraceResponse);
                setLoading(false);
              })
              .catch((err) => {
                console.error("Failed to reload trace:", err);
                setLoading(false);
              });
          }}
          style={refreshButtonStyle}
        >
          ⟳ Refresh
        </button>
      </header>

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
          {traces.length === 0 ? (
            <p style={{ opacity: 0.7 }}>No traces recorded yet.</p>
          ) : (
            <>
              <div style={heatmapLegendStyle}>
                <span>Fast</span>
                <span style={{ background: "#1b5e20", width: 40, height: 10 }} />
                <span style={{ background: "#33691e", width: 40, height: 10 }} />
                <span style={{ background: "#f9a825", width: 40, height: 10 }} />
                <span style={{ background: "#e53935", width: 40, height: 10 }} />
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
                    {traces.map((t) => (
                      <tr
                        key={t.id}
                        onClick={() => setSelectedTraceId(t.id)}
                        style={{
                          cursor: "pointer",
                          backgroundColor:
                            selectedTrace?.id === t.id ? "#252a39" : "transparent",
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
                    ))}
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
  fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 16,
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
