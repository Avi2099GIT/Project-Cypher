import React, { useEffect, useMemo, useState } from "react";

/* ======================== TYPES ======================== */

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

/* ======================== APP ======================== */

export default function TraceInspectorApp() {
  const [data, setData] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  // ---------- Plan state ----------
  const [plan, setPlan] = useState<any>(null);
  const [planLoading, setPlanLoading] = useState(false);

  // ---------- Metrics state ----------
  const [metrics, setMetrics] = useState<any>(null);

  // ---------- Filters ----------
  const [live, setLive] = useState(true);
  const [traceSearch, setTraceSearch] = useState("");
  const [nodeFilter, setNodeFilter] = useState("");
  const [minMs, setMinMs] = useState(0);
  const [showFailedOnly, setShowFailedOnly] = useState(false);
  const [slowLimit, setSlowLimit] = useState(300);
  const [criticalLimit, setCriticalLimit] = useState(800);

  /* ======================== LOAD TRACE ======================== */

  const load = () => {
    fetch("http://127.0.0.1:8000/v1/assistant/debug/trace")
      .then((res) => res.json())
      .then((json) => {
        setData(json);
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

  /* ======================== LOAD PLAN ======================== */

  useEffect(() => {
    if (!selectedTraceId) return;

    setPlanLoading(true);
    fetch(
      `http://127.0.0.1:8000/v1/assistant/debug/plan?trace_id=${selectedTraceId}`
    )
      .then((res) => res.json())
      .then((json) => {
        setPlan(json);
        setPlanLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load plan:", err);
        setPlan(null);
        setPlanLoading(false);
      });
  }, [selectedTraceId]);

  /* ======================== LOAD METRICS ======================== */

  useEffect(() => {
    fetch("http://127.0.0.1:8000/v1/assistant/debug/metrics")
      .then((r) => r.json())
      .then(setMetrics)
      .catch(() => {
        // metrics are nice-to-have, never break UI
      });
  }, []);

  /* ======================== DERIVED ======================== */

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
    for (const list of byId.values())
      list.sort((a, b) => a.timestamp - b.timestamp);
    return Array.from(byId.entries()).map(([id, evs]) => ({ id, events: evs }));
  }, [events]);

  const slowestNodes: SlowNode[] = (data?.slowest as any) ?? [];

  const filteredTraces = useMemo(() => {
    return traces.filter((t) => {
      if (traceSearch && !t.id.includes(traceSearch)) return false;

      if (nodeFilter) {
        const match = t.events.some((e) =>
          e.node.toLowerCase().includes(nodeFilter.toLowerCase())
        );
        if (!match) return false;
      }

      if (showFailedOnly) {
        const hasFail = t.events.some(
          (e) => e.status === "FAILED" || e.status === "ERROR"
        );
        if (!hasFail) return false;
      }

      if (minMs > 0) {
        const slow = t.events.some(
          (e) => {
          const d = extractDuration(e);
          return d != null && d >= minMs;
        }
        );
        if (!slow) return false;
      }

      return true;
    });
  }, [traces, traceSearch, nodeFilter, showFailedOnly, minMs]);

  const visibleTraces = filteredTraces.length > 0 ? filteredTraces : traces;

  const selectedTrace =
    selectedTraceId != null
      ? visibleTraces.find((t) => t.id === selectedTraceId)
      : visibleTraces[visibleTraces.length - 1];

  /* ======================== HELPERS ======================== */

  function extractDuration(ev?: TraceEvent): number | null {
    if (!ev) return null;

    // 1️⃣ Prefer structured duration from backend
    if (typeof ev.extra?.duration_ms === "number") {
      return ev.extra.duration_ms;
    }

    // 2️⃣ Parse from message text (fallback)
    if (typeof ev.message === "string") {
      const match = ev.message.match(/([\d.]+)\s*(ms|s)/i);
      if (match) {
        const value = parseFloat(match[1]);
        return match[2].toLowerCase() === "s" ? value * 1000 : value;
      }
    }

    return null;
  }


  function cellColor(ev?: TraceEvent): string {
    if (!ev) return "#222"; // skipped

    const dur = extractDuration(ev);

    if (ev.status === "FAILED" || ev.status === "ERROR") return "#8b1e3f";
    if (dur == null) return "#333"; // no timing info

    if (dur >= criticalLimit) return "#e53935";
    if (dur >= slowLimit) return "#f9a825";
    if (dur > 0) return "#1b5e20"; // ✅ finally GREEN

    return "#333";
  }

  function formatMs(ms?: number) {
    if (ms == null) return "";
    if (ms < 1000) return `${ms.toFixed(1)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
  }

  /* ======================== UI ======================== */

  if (loading) return <div style={pageStyle}>Loading…</div>;
  if (!data) return <div style={pageStyle}>Failed to load trace data.</div>;

  return (
    <div style={pageStyle}>
      <header style={headerStyle}>
        <div>
          <h1 style={{ margin: 0 }}>🧠 Cypher Trace Heatmap</h1>
          <small>Phase-4 · Agent orchestration · Execution observability</small>
        </div>
        <button onClick={load} style={refreshButtonStyle}>
          ⟳ Refresh
        </button>
      </header>

      {/* CONTROLS */}
      <div style={controlsRowStyle}>
        <label>
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => setLive(e.target.checked)}
          />{" "}
          Live
        </label>

        <input
          placeholder="Trace ID"
          value={traceSearch}
          onChange={(e) => setTraceSearch(e.target.value)}
        />
        <input
          placeholder="Node"
          value={nodeFilter}
          onChange={(e) => setNodeFilter(e.target.value)}
        />
        <input
          type="number"
          placeholder="Min ms"
          value={minMs}
          onChange={(e) => setMinMs(+e.target.value || 0)}
        />
        <input
          type="number"
          placeholder="Slow ≥"
          value={slowLimit}
          onChange={(e) => setSlowLimit(+e.target.value)}
        />
        <input
          type="number"
          placeholder="Critical ≥"
          value={criticalLimit}
          onChange={(e) => setCriticalLimit(+e.target.value)}
        />

        <label>
          <input
            type="checkbox"
            checked={showFailedOnly}
            onChange={(e) => setShowFailedOnly(e.target.checked)}
          />{" "}
          Failed
        </label>
      </div>

      {/* SUMMARY */}
      <section style={summaryRowStyle}>
        <Card title="Summary">
          <SummaryStat label="Events" value={data.summary.total_events} />
          <SummaryStat
            label="Nodes"
            value={Object.keys(data.summary.per_node).length}
          />
          <SummaryStat label="Failures" value={data.summary.failures} />
        </Card>

        <Card title="Slowest Nodes">
          {slowestNodes.length === 0 ? (
            <small>No duration data yet.</small>
          ) : (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Total</th>
                  <th>Count</th>
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
        </Card>
      </section>

      {/* EXECUTION METRICS */}
      <Card title="Execution Metrics">
        {!metrics ? (
          <small>Loading metrics…</small>
        ) : (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th>Node</th>
                <th>Avg ms</th>
                <th>Calls</th>
                <th>Fails</th>
                <th>Fail %</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {metrics.nodes.map((n: any) => (
                <tr key={n.node}>
                  <td>
                    <code>{n.node}</code>
                  </td>
                  <td>{n.avg_ms}</td>
                  <td>{n.calls}</td>
                  <td>{n.failures}</td>
                  <td>{n.failure_rate}%</td>
                  <td>{n.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* HEATMAP + DETAILS */}
      <section style={bottomRowStyle}>
        <Card title="Execution Heatmap" flex={2}>
          {/* HEATMAP LEGEND */}
          <div style={heatmapLegend}>
            <LegendItem
              color="#1b5e20"
              label="Healthy"
              desc="Executed within normal time"
            />
            <LegendItem
              color="#f9a825"
              label="Slow"
              desc={`>${slowLimit} ms`}
            />
            <LegendItem
              color="#e53935"
              label="Critical"
              desc={`>${criticalLimit} ms`}
            />
            <LegendItem
              color="#8b1e3f"
              label="Failed"
              desc="Execution error"
            />
            <LegendItem
              color="#333"
              label="No Duration"
              desc="Completed but no timing info"
            />
            <LegendItem
              color="#222"
              label="Skipped"
              desc="Node did not run"
            />
          </div>

          <table style={heatmapTableStyle}>
            <thead>
              <tr>
                <th>Trace</th>
                {nodes.map((n) => (
                  <th key={n}>{n}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleTraces.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => setSelectedTraceId(t.id)}
                  style={{
                    background:
                      selectedTrace?.id === t.id ? "#263043" : "transparent",
                    cursor: "pointer",
                  }}
                >
                  <td>
                    <code>{t.id.slice(0, 8)}</code>
                  </td>
                  {nodes.map((n) => {
                    const ev =
                      [...t.events]
                        .filter((e) => e.node === n)
                        .sort((a, b) => {
                          const p = (s: string) =>
                            s === "SUCCESS" ? 3 : s === "FAILED" ? 2 : s === "RUNNING" ? 1 : 0;
                          return p(b.status) - p(a.status);
                        })[0] || undefined;

                    const dur = extractDuration(ev) ?? undefined;
                    return (
                      <td key={n}>
                        <div
                          title={
                            ev
                              ? `${ev.node} | ${ev.status} | ${
                                  dur !== undefined ? formatMs(dur) : ""
                                }`
                              : ""
                          }
                          style={{
                            height: 14,
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
        </Card>

        <Card title="Trace Details" flex={1}>
          {!selectedTrace ? (
            <small>Select a trace</small>
          ) : (
            <>
              <small>
                <code>{selectedTrace.id}</code>
              </small>
              <ol>
                {selectedTrace.events.map((e) => (
                  <li key={e.timestamp}>
                    <strong>{e.node}</strong> — {e.status} —{" "}
                    {(() => {
                      const d = extractDuration(e);
                      return d != null ? formatMs(d) : "";
                    })()}
                  </li>
                ))}
              </ol>

              <hr />

              <h3>Plan Inspector</h3>

              {planLoading && <small>Loading plan…</small>}

              {!planLoading && !plan?.plan && <small>No plan available.</small>}

              {plan?.plan && (
                <>
                  <h4>Why this plan?</h4>

                  <pre style={jsonBox}>
                    {JSON.stringify(plan.plan.explanation, null, 2)}
                  </pre>

                  <h4>Score Breakdown</h4>

                  <pre style={jsonBox}>
                    {JSON.stringify(plan.plan.score, null, 2)}
                  </pre>

                  <h4>Execution Steps</h4>

                  <ol>
                    {plan.plan.steps.map((s: any, i: number) => (
                      <li key={i}>
                        <code>{s.tool}</code> — {JSON.stringify(s.args)}
                      </li>
                    ))}
                  </ol>

                  {plan.plan.rejected?.length > 0 && (
                    <>
                      <h4>Rejected Plans</h4>
                      {plan.plan.rejected.map((r: any, i: number) => (
                        <pre key={i} style={jsonBox}>
                          {JSON.stringify(r, null, 2)}
                        </pre>
                      ))}
                    </>
                  )}

                  {plan.debug && (
                    <>
                      <h4>Ranked Candidates</h4>
                      <pre style={jsonBox}>
                        {JSON.stringify(plan.debug, null, 2)}
                      </pre>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </Card>
      </section>
    </div>
  );
}

/* ======================== COMPONENTS ======================== */

function Card({ title, children, flex = 1 }: any) {
  return (
    <section style={{ ...cardStyle, flex }}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div style={summaryBox}>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function Tag({ children, color }: any) {
  return (
    <span
      style={{
        background: color + "33",
        color,
        padding: "2px 6px",
        borderRadius: 6,
        fontSize: 11,
      }}
    >
      {children}
    </span>
  );
}

function LegendItem({ color, label, desc }: any) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        fontSize: 11,
      }}
    >
      <div
        style={{
          width: 14,
          height: 14,
          background: color,
          borderRadius: 4,
          border: "1px solid #444",
        }}
      />
      <div>
        <strong>{label}</strong>
        <div style={{ opacity: 0.7 }}>{desc}</div>
      </div>
    </div>
  );
}

/* ======================== STYLES ======================== */

const pageStyle = {
  background: "#050712",
  color: "#e5e7eb",
  minHeight: "100vh",
  padding: 16,
  fontFamily: "system-ui",
};

const headerStyle = {
  display: "flex",
  justifyContent: "space-between",
  marginBottom: 8,
};

const heatmapLegend: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 12,
  marginBottom: 10,
};

const controlsRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  marginBottom: 10,
  flexWrap: "wrap" as React.CSSProperties["flexWrap"],
};

const summaryRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 12,
};

const bottomRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 12,
  marginTop: 12,
};

const cardStyle: React.CSSProperties = {
  background: "#0b0f1d",
  padding: 12,
  borderRadius: 10,
  border: "1px solid #111827",
};

const summaryBox: React.CSSProperties = {
  background: "#151827",
  padding: 10,
  borderRadius: 8,
  marginBottom: 6,
};

const refreshButtonStyle: React.CSSProperties = {
  borderRadius: 20,
  padding: "6px 12px",
  border: "1px solid #4b5563",
  background: "#111827",
  color: "#e5e7eb",
};

const heatmapTableStyle: React.CSSProperties = {
  width: "100%",
  fontSize: 11,
  borderCollapse: "collapse" as const,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  fontSize: 12,
};

const jsonBox: React.CSSProperties = {
  background: "#020617",
  padding: 8,
  borderRadius: 6,
  fontSize: 11,
  marginTop: 6,
  overflow: "auto",
  maxHeight: 180,
};

const rejectedCard: React.CSSProperties = {
  background: "#0f172a",
  padding: 8,
  marginTop: 6,
  borderRadius: 8,
};
