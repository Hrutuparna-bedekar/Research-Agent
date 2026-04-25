import { deleteSession } from "../api";

const STATUS_COLORS = { running: "running", done: "done", error: "error" };

function timeAgo(isoStr) {
  if (!isoStr) return "";
  const diff = (Date.now() - new Date(isoStr + "Z")) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew, onDeleted }) {
  const handleDelete = async (e, id) => {
    e.stopPropagation();
    await deleteSession(id);
    onDeleted(id);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">🔬</div>
          <span className="sidebar-logo-text">ResearchAI</span>
        </div>
        <button className="new-chat-btn" onClick={onNew}>
          <span>✚</span>
          New Research
        </button>
      </div>

      {sessions.length > 0 && (
        <p className="sidebar-section-title">Recent Sessions</p>
      )}

      <div className="session-list">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className={`session-item ${s.session_id === activeId ? "active" : ""}`}
            onClick={() => onSelect(s)}
          >
            <div className={`session-dot ${STATUS_COLORS[s.status] ?? ""}`} />
            <div className="session-info">
              <div className="session-query">{s.query}</div>
              <div className="session-meta">
                {s.status === "running" ? "Researching…" :
                 s.status === "done"    ? `✓ Done · ${s.has_report ? "Report ready" : ""}` :
                 s.status === "error"   ? "⚠ Error" : "Pending"}
                {" · "}{timeAgo(s.started_at)}
              </div>
            </div>
            <button
              className="session-delete"
              title="Delete session"
              onClick={(e) => handleDelete(e, s.session_id)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                <line x1="10" y1="11" x2="10" y2="17"></line>
                <line x1="14" y1="11" x2="14" y2="17"></line>
              </svg>
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
