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

const NODE_ICONS = {
  stm_summarize:       "🧠",
  analyze_query:       "🔍",
  execute_plan:        "🌐",
  summarize_findings:  "📝",
  reflect:             "🤔",
  advance_plan:        "➡️",
  generate_gap_queries:"🔎",
  generate_report:     "✍️",
};

/* ── ProgressTracker ─────────────────────────────────────── */
export function ProgressTracker({ nodeStates }) {
  const seenNodes = Object.keys(nodeStates);
  const visibleNodes = NODE_ORDER.filter((n) => seenNodes.includes(n) || n === "generate_report");

  return (
    <div className="progress-bubble">
      <div className="progress-header">
        <span style={{ fontSize: "0.9rem" }}>⚡</span>
        <span className="progress-label">Research in Progress</span>
      </div>
      <div className="progress-steps">
        {visibleNodes.map((node) => {
          const state = nodeStates[node];
          const status = state?.status ?? "pending";
          const meta   = state?.meta;
          return (
            <div key={node} className={`progress-step ${status}`}>
              <div className={`step-icon ${status}`}>
                {status === "active"  ? "↻" :
                 status === "done"    ? "✓" :
                 NODE_ICONS[node] ?? "·"}
              </div>
              <span className={`step-label ${status}`}>
                {state?.label ?? node}
              </span>
              {meta && (
                <span className="step-meta">
                  {typeof meta === "object"
                    ? Object.entries(meta).map(([k,v]) => `${k}: ${v}`).join(" · ")
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
    <div className="report-bubble">
      {confidence != null && (
        <div className="confidence-badge">
          📊 Confidence: {Math.round(confidence * 100)}%
        </div>
      )}
      <div className="report-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {text}
        </ReactMarkdown>
        {isStreaming && <span className="cursor" />}
      </div>
    </div>
  );
}

/* ── UserBubble ──────────────────────────────────────────── */
export function UserBubble({ text }) {
  return (
    <div className="message-row user">
      <div className="avatar" style={{ background: '#e0e7ff', color: '#4f46e5' }}>👤</div>
      <div className="bubble user">{text}</div>
    </div>
  );
}

/* ── AgentBubble (plain text) ────────────────────────────── */
export function AgentBubble({ children }) {
  return (
    <div className="message-row">
      <div className="avatar" style={{ background: 'linear-gradient(135deg, #a78bfa, #6366f1)', color: 'white' }}>✨</div>
      <div className="bubble agent">{children}</div>
    </div>
  );
}

/* ── TypingIndicator ─────────────────────────────────────── */
export function TypingIndicator() {
  return (
    <div className="message-row">
      <div className="avatar" style={{ background: 'linear-gradient(135deg, #a78bfa, #6366f1)', color: 'white' }}>✨</div>
      <div className="bubble agent">
        <div className="typing-dots">
          <span /><span /><span />
        </div>
      </div>
    </div>
  );
}
