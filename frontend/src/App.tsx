import { useEffect, useRef, useState } from "react";

interface Anomaly {
  timestamp: number | string;
  severity_score: number;
  is_anomaly: boolean;
  log_entry: Record<string, unknown>;
  explanation: string;
}

const METRIC_KEYS = ["error_count", "latency_ms", "memory_used_mb", "request_count"];

function formatTimestamp(ts: number | string): string {
  // CloudWatch sends epoch ms (number), fallback is ISO string — both work with Date()
  return new Date(ts).toLocaleString();
}

function formatMetrics(log_entry: Record<string, unknown>): string {
  return METRIC_KEYS
    .filter((k) => log_entry[k] !== undefined)
    .map((k) => `${k}: ${log_entry[k]}`)
    .join(" · ");
}

export default function App() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket("ws://localhost:8000/ws/logs");
      wsRef.current = ws;

      ws.onopen = () => setStatus("connected");

      ws.onmessage = (event) => {
        const data: Anomaly = JSON.parse(event.data);
        setAnomalies((prev) => [data, ...prev].slice(0, 50));
      };

      ws.onclose = () => {
        setStatus("disconnected");
        // auto-reconnect after 3s — FastAPI might restart during dev
        setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    };

    connect();
    return () => wsRef.current?.close();
  }, []);

  const statusColor = {
    connecting: "#f59e0b",
    connected: "#10b981",
    disconnected: "#ef4444",
  }[status];

  return (
    <div style={{ fontFamily: "monospace", background: "#0f172a", minHeight: "100vh", padding: "2rem", color: "#e2e8f0" }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "#f8fafc", margin: 0 }}>
            🔍 Cloud Observability Agent
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: statusColor }} />
            <span style={{ fontSize: "0.85rem", color: statusColor, textTransform: "uppercase" }}>{status}</span>
          </div>
        </div>

        {/* Stats bar */}
        <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
          {[
            { label: "Total Anomalies", value: anomalies.length },
            {
              label: "Avg Severity",
              value: anomalies.length
                ? (anomalies.reduce((a, b) => a + b.severity_score, 0) / anomalies.length).toFixed(3)
                : "—",
            },
            {
              label: "Latest",
              value: anomalies[0] ? formatTimestamp(anomalies[0].timestamp) : "—",
            },
          ].map(({ label, value }) => (
            <div key={label} style={{ flex: 1, background: "#1e293b", borderRadius: 8, padding: "1rem", border: "1px solid #334155" }}>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#f8fafc" }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Live feed */}
        <div style={{ background: "#1e293b", borderRadius: 8, border: "1px solid #334155", overflow: "hidden" }}>
          <div style={{ padding: "1rem 1.25rem", borderBottom: "1px solid #334155", fontSize: "0.85rem", color: "#94a3b8" }}>
            LIVE ANOMALY FEED
          </div>

          {anomalies.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#475569" }}>
              {status === "connected" ? "Waiting for anomalies — logs polled every 10s" : "Not connected to FastAPI"}
            </div>
          ) : (
            anomalies.map((a, i) => (
              <div
                key={i}
                style={{
                  padding: "1rem 1.25rem",
                  borderBottom: "1px solid #0f172a",
                  background: i % 2 === 0 ? "#1e293b" : "#162032",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span style={{ color: "#f97316", fontWeight: 700 }}>ANOMALY</span>
                  <span style={{ color: "#64748b", fontSize: "0.8rem" }}>
                    {formatTimestamp(a.timestamp)}
                  </span>
                </div>
                <div style={{ fontSize: "0.85rem", color: "#94a3b8", marginBottom: 6 }}>
                  Severity: <span style={{ color: "#fb923c" }}>{a.severity_score.toFixed(4)}</span>
                  {" · "}
                  {formatMetrics(a.log_entry)}
                </div>
                <div style={{ fontSize: "0.85rem", color: "#cbd5e1", background: "#0f172a", borderRadius: 6, padding: "0.5rem 0.75rem" }}>
                  {a.explanation}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}