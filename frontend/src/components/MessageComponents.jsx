import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const NODE_ORDER = [
  "stm_summarize",
  "analyze_query",
  "execute_plan",
  "summarize_findings",
  "reflect",
  "advance_plan",
  "generate_gap_queries",
  "generate_report",
];

const NODE_LABELS = {
  stm_summarize:        "Summarising context",
  analyze_query:        "Analysing query",
  execute_plan:         "Searching the web",
  summarize_findings:   "Extracting findings",
  reflect:              "Evaluating completeness",
  advance_plan:         "Advancing plan",
  generate_gap_queries: "Identifying gaps",
  generate_report:      "Writing report",
};

/* ── ProgressTracker ─────────────────────────────────────── */
export function ProgressTracker({ nodeStates }) {
  const seenNodes = Object.keys(nodeStates);
  const visibleNodes = NODE_ORDER.filter(
    (n) => seenNodes.includes(n) || n === "generate_report"
  );

  return (
    <div className="bubble agent" style={{ padding: "14px 16px" }}>
      <div className="progress-header">
        <span className="sparkle">◈</span>
        <span className="progress-label">Researching</span>
      </div>
      <div className="progress-steps">
        {visibleNodes.map((node) => {
          const st     = nodeStates[node];
          const status = st?.status ?? "pending";
          const meta   = st?.meta;
          return (
            <div key={node} className={`progress-step ${status}`}>
              <div className={`step-icon ${status}`}>
                {status === "active" ? "↻" : status === "done" ? "✓" : "·"}
              </div>
              <span className={`step-label ${status}`}>
                {st?.label ?? NODE_LABELS[node] ?? node}
              </span>
              {meta && (
                <span className="step-meta">
                  {typeof meta === "object"
                    ? Object.entries(meta)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · ")
                    : meta}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── ReportView ──────────────────────────────────────────── */
export function ReportView({ text, isStreaming, confidence }) {
  return (
    <div className="report-bubble bubble agent" style={{ padding: "16px 20px", flex: 1, minWidth: 0, overflow: "hidden" }}>
      {confidence != null && (
        <div className="confidence-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="16 12 12 8 8 12"/><line x1="12" y1="16" x2="12" y2="8"/></svg>
          Confidence: {Math.round(confidence * 100)}%
        </div>
      )}
      <div className="report-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        {isStreaming && <span className="cursor" />}
      </div>
    </div>
  );
}

/* ── UserBubble ──────────────────────────────────────────── */
export function UserBubble({ text }) {
  return (
    <div className="message-row user">
      <div className="avatar" style={{ background: "#1d2d3e", color: "#60a5fa", fontSize: "11px", fontWeight: 600 }}>
        You
      </div>
      <div className="bubble user">{text}</div>
    </div>
  );
}

/* ── AgentBubble (plain text / errors) ──────────────────── */
export function AgentBubble({ children }) {
  return (
    <div className="message-row">
      <AgentAvatar />
      <div className="bubble agent">{children}</div>
    </div>
  );
}

/* ── AgentAvatar ─────────────────────────────────────────── */
export function AgentAvatar() {
  return (
    <div
      className="avatar"
      style={{
        background: "linear-gradient(135deg, #6366f1, #3b82f6)",
        color: "white",
        fontSize: "12px",
        fontWeight: 700,
        letterSpacing: "-0.02em",
      }}
    >
      AI
    </div>
  );
}

/* ── TypingIndicator ─────────────────────────────────────── */
export function TypingIndicator() {
  return (
    <div className="message-row">
      <AgentAvatar />
      <div className="bubble agent" style={{ padding: "14px 16px" }}>
        <div className="typing-dots">
          <span /><span /><span />
        </div>
      </div>
    </div>
  );
}
