import { useState, useEffect, useRef, useReducer, useCallback } from "react";
import "./index.css";

import { startResearch, getSessions, BASE } from "./api";
import { useSSE } from "./hooks/useSSE";
import { SessionSidebar } from "./components/SessionSidebar";
import { ExportButton } from "./components/ExportButton";
import {
  UserBubble,
  AgentBubble,
  AgentAvatar,
  TypingIndicator,
  ProgressTracker,
  ReportView,
} from "./components/MessageComponents";

// ── Suggestions ────────────────────────────────────────────
const SUGGESTIONS = [
  "What is quantum computing?",
  "Compare LLMs vs traditional NLP approaches",
  "How does CRISPR gene editing work?",
  "Explain transformer architecture in depth",
];

// ── Message type constants ──────────────────────────────────
const MSG_USER     = "user";
const MSG_PROGRESS = "progress";
const MSG_REPORT   = "report";
const MSG_ERROR    = "error";

// ── Reducer ────────────────────────────────────────────────
function chatReducer(state, action) {
  switch (action.type) {

    case "NEW_QUERY": return {
      ...state,
      messages:   [...state.messages, { type: MSG_USER, text: action.query, id: Date.now() }],
      nodeStates: {},
      reportText: "",
      isStreaming: false,
      isDone:     false,
      confidence: null,
    };

    case "NODE_START": {
      const ns = { ...state.nodeStates,
        [action.node]: { status: "active", label: action.label, meta: null }
      };
      // Mark others active→done if a later node starts
      return { ...state, nodeStates: ns, isStreaming: true };
    }

    case "NODE_DONE": {
      const ns = { ...state.nodeStates,
        [action.node]: {
          ...state.nodeStates[action.node],
          status: "done",
          meta: action.data,
        }
      };
      return { ...state, nodeStates: ns };
    }

    case "LOAD_SESSION": {
      const messages = action.messages || [{ type: MSG_USER, text: action.query, id: Date.now() }];
      return {
        messages:   messages,
        nodeStates: {},
        reportText: action.report || "",
        isStreaming: false,
        isDone:     !!action.report,
        confidence: action.confidence || null,
      };
    }

    case "REPORT_CHUNK":
      return { ...state, reportText: state.reportText + action.chunk };

    case "DONE": {
      const newMessages = [...state.messages];
      if (state.reportText) {
        newMessages.push({
          type: MSG_REPORT,
          text: state.reportText,
          id: Date.now(),
          confidence: state.confidence
        });
      }
      return { ...state, isStreaming: false, isDone: true, messages: newMessages, reportText: "" };
    }

    case "ERROR": return {
      ...state,
      isStreaming: false,
      isDone: true,
      messages: [...state.messages,
        { type: MSG_ERROR, text: action.message, id: Date.now() }
      ],
      reportText: "",
    };

    case "SET_CONFIDENCE":
      return { ...state, confidence: action.confidence };

    default: return state;
  }
}

const initialChat = {
  messages:   [],
  nodeStates: {},
  reportText: "",
  isStreaming: false,
  isDone:     false,
  confidence: null,
};

// ── App ────────────────────────────────────────────────────
export default function App() {
  const [sessions, setSessions]       = useState([]);
  const [activeSessionId, setActive]  = useState(null);
  const [chat, dispatch]              = useReducer(chatReducer, initialChat);
  const [input, setInput]             = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  const messagesEndRef = useRef(null);
  const textareaRef    = useRef(null);

  // ── Load sessions on mount ────────────────────────────────
  useEffect(() => {
    getSessions()
      .then((d) => setSessions(d.sessions ?? []))
      .catch(console.error);
  }, []);

  // ── Auto-scroll ───────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.reportText, chat.nodeStates]);

  // ── SSE event handler ─────────────────────────────────────
  const handleSSEEvent = useCallback((event) => {
    switch (event.type) {
      case "node_start":
        dispatch({ type: "NODE_START", node: event.node, label: event.label });
        break;
      case "node_done":
        dispatch({ type: "NODE_DONE", node: event.node, data: event.data });
        if (event.node === "reflect" && event.data?.confidence != null) {
          dispatch({ type: "SET_CONFIDENCE", confidence: event.data.confidence });
        }
        break;
      case "report_chunk":
        dispatch({ type: "REPORT_CHUNK", chunk: event.data.chunk });
        break;
      case "done":
        dispatch({ type: "DONE" });
        // Refresh session list
        getSessions().then((d) => setSessions(d.sessions ?? []));
        break;
      case "error":
        dispatch({ type: "ERROR", message: event.data.message });
        break;
    }
  }, []);

  const handleSSEDone = useCallback(() => {
    setSubmitting(false);
  }, []);

  // ── SSE hook ──────────────────────────────────────────────
  useSSE(
    isSubmitting ? activeSessionId : null,
    handleSSEEvent,
    handleSSEDone,
  );

  // ── Submit query ──────────────────────────────────────────
  const handleSubmit = async (query) => {
    const q = (query ?? input).trim();
    if (!q || isSubmitting) return;
    setInput("");
    setSubmitting(true);
    dispatch({ type: "NEW_QUERY", query: q });

    try {
      const { session_id } = await startResearch(q, activeSessionId);
      if (!activeSessionId) setActive(session_id);
      
      setSessions((prev) => {
        const exists = prev.find(s => s.session_id === session_id);
        if (exists) return prev; // Don't duplicate in sidebar
        return [
          { session_id, query: q, status: "running", started_at: new Date().toISOString() },
          ...prev,
        ];
      });
    } catch (err) {
      dispatch({ type: "ERROR", message: err.message });
      setSubmitting(false);
    }
  };

  // ── Load past session ─────────────────────────────────────
  const handleSelectSession = (session) => {
    setActive(session.session_id);
    
    Promise.all([
      fetch(`${BASE}/research/${session.session_id}/history`).then(r => r.json()),
      fetch(`${BASE}/research/${session.session_id}/report`).then(r => r.json()),
    ]).then(([historyData, reportData]) => {
      const history = (historyData.history || []).map(m => ({
        type: m.type === "user" ? MSG_USER : MSG_REPORT,
        text: m.text,
        id:   Math.random()
      }));

      dispatch({ 
        type: "LOAD_SESSION", 
        query: session.query, 
        messages: history.length > 0 ? history : null,
        report: reportData.report, 
        confidence: reportData.confidence 
      });
    }).catch(console.error);
  };

  // ── Textarea auto-resize + Enter to submit ────────────────
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleTextareaChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  };

  // ── Derived ───────────────────────────────────────────────
  const researchNodes = ["analyze_query", "execute_plan", "summarize_findings", "reflect", "advance_plan", "generate_gap_queries", "generate_report"];
  const hasProgress  = Object.keys(chat.nodeStates).some(node => researchNodes.includes(node));
  const hasHistoryReport = chat.messages.some(m => m.type === MSG_REPORT);
  const canExport    = chat.isDone && (hasHistoryReport || chat.reportText.length > 0);
  const showTyping   = isSubmitting && !hasProgress;
  const activeQuery  = chat.messages.find((m) => m.type === MSG_USER)?.text ?? "";

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="app-shell">
      <SessionSidebar
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={handleSelectSession}
        onNew={() => {
          setActive(null);
          dispatch({ type: "NEW_QUERY", query: "" });
          setInput("");
          setSubmitting(false);
          // clear chat
          dispatch({ type: "DONE" });
          window.location.reload(); // simplest reset
        }}
        onDeleted={(id) => {
          setSessions((prev) => prev.filter((s) => s.session_id !== id));
          if (id === activeSessionId) setActive(null);
        }}
      />

      <div className="main">
        {/* Header */}
        <div className="chat-header">
          <span className="header-title">
            {activeQuery || "Research Agent"}
          </span>
          <div className="header-actions">
            <ExportButton sessionId={activeSessionId} disabled={!canExport} />
          </div>
        </div>

        {/* Messages */}
        <div className="messages-area">
          {chat.messages.length === 0 ? (
            /* Empty state */
            <div className="empty-state">
              <div className="zeno-sphere-container">
                <h1>Research Agent</h1>
                <p>Ask anything — I'll research it in depth and deliver a structured report.</p>
              </div>
              <div className="suggestion-chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="chip" onClick={() => handleSubmit(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {/* Historical messages */}
              {chat.messages.map((m) => {
                if (m.type === MSG_USER) return <UserBubble key={m.id} text={m.text} />;
                if (m.type === MSG_REPORT) return (
                  <div key={m.id} className="message-row">
                    <AgentAvatar />
                    <ReportView text={m.text} isStreaming={false} confidence={m.confidence} />
                  </div>
                );
                if (m.type === MSG_ERROR) return (
                  <AgentBubble key={m.id}>⚠ {m.text}</AgentBubble>
                );
                return null;
              })}

              {/* Typing indicator (only if not yet streaming a report) */}
              {showTyping && !chat.reportText && <TypingIndicator />}

              {/* Progress tracker */}
              {hasProgress && !chat.reportText && (
                <div className="message-row">
                  <AgentAvatar />
                  <ProgressTracker nodeStates={chat.nodeStates} />
                </div>
              )}

              {/* ACTIVE Streaming/current report */}
              {chat.reportText && (
                <div className="message-row">
                  <AgentAvatar />
                  <ReportView
                    text={chat.reportText}
                    isStreaming={chat.isStreaming}
                    confidence={chat.confidence}
                  />
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className="input-bar">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              className="input-textarea"
              placeholder="Ask a research question… (Enter to send, Shift+Enter for newline)"
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isSubmitting}
            />
            <button
              className="send-btn"
              onClick={() => handleSubmit()}
              disabled={!input.trim() || isSubmitting}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
