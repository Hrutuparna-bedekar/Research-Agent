
import asyncio
import json
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from session import Session, session_manager  


_wf = None


def _get_wf():
    global _wf
    if _wf is None:
        from agent import wf  
        _wf = wf
    return _wf


_executor = ThreadPoolExecutor(max_workers=4)

# Delay between streamed word-chunks (seconds).
# Increase to slow down, decrease to speed up.
# Override via STREAM_DELAY_MS env var (e.g. STREAM_DELAY_MS=50 for slower).
_CHUNK_DELAY: float = int(os.getenv("STREAM_DELAY_MS", "30")) / 1000.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _node_summary(node_name: str, node_output: dict) -> dict:
    """Extract a human-readable summary from a node's output dict."""
    if node_name == "analyze_query":
        return {
            "complexity": node_output.get("complexity", ""),
            "research_type": node_output.get("research_type", ""),
            "steps": len(node_output.get("plan", [])),
        }
    if node_name == "execute_plan":
        docs = node_output.get("documents", [])
        visited = node_output.get("visited_queries", [])
        return {"docs_fetched": len(docs), "queries_run": len(visited)}
    if node_name == "reflect":
        return {
            "confidence": round(node_output.get("confidence", 0), 2),
            "missing": len(node_output.get("missing_topics", [])),
        }
    if node_name == "summarize_findings":
        findings = node_output.get("findings", [])
        return {"findings_count": len(findings)}
    if node_name == "generate_gap_queries":
        return {"gap_queries": node_output.get("current_queries", [])}
    if node_name == "generate_report":
        return {}  # report comes via report_chunk events
    return {}


NODE_LABELS = {
    "stm_summarize":       "Recalling previous research…",
    "analyze_query":       "Planning research strategy…",
    "execute_plan":        "Searching the web…",
    "summarize_findings":  "Extracting key findings…",
    "reflect":             "Evaluating completeness…",
    "advance_plan":        "Advancing to next step…",
    "generate_gap_queries":"Identifying knowledge gaps…",
    "router_node":         "Analyzing request…",
    "generate_report":     "Writing report…",
    "chat_response":       "Thinking…",
}


# ── main thread function ──────────────────────────────────────────────────────

def _run_agent_thread(session: Session, loop: asyncio.AbstractEventLoop):
    """
    Runs in a ThreadPoolExecutor thread.
    Calls wf.stream() synchronously, converts each chunk to an SSE event,
    and broadcasts it to all subscribers via the event loop.
    """
    def put(event: dict):
        loop.call_soon_threadsafe(session.broadcast, event)

    try:
        wf = _get_wf()
        # Thread-safe status update
        with session._lock:
            session.status = "running"
        session_manager.update(session)

        input_state = {
            "query":    session.query,
            "messages": [],
        }
        config = {"configurable": {"thread_id": session.thread_id}}

        for chunk in wf.stream(input_state, config=config, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue

                # Node started
                put({
                    "type": "node_start",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "data": {},
                })

                if (node_name in ("generate_report", "chat_response")) and "final_output" in node_output:
                    report_text = node_output["final_output"]
                    with session._lock:
                        session.report = report_text
                    words = report_text.split(" ")
                    chunk_size = 3 
                    for i in range(0, len(words), chunk_size):
                        chunk_text = " ".join(words[i:i+chunk_size]) + " "
                        put({
                            "type": "report_chunk",
                            "node": node_name,
                            "data": {"chunk": chunk_text},
                        })
                        time.sleep(_CHUNK_DELAY)

                if node_name == "reflect":
                    with session._lock:
                        session.confidence  = node_output.get("confidence", 0)

                # Node done
                put({
                    "type": "node_done",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "data": _node_summary(node_name, node_output),
                })

        with session._lock:
            session.status = "done"
            import datetime
            session.finished_at = datetime.datetime.utcnow()
        session_manager.update(session)
        put({"type": "done", "node": None, "data": {"session_id": session.session_id}})

    except Exception as exc:
        with session._lock:
            session.status = "error"
        session_manager.update(session)
        put({"type": "error", "node": None, "data": {"message": str(exc)}})


# ── public API ────────────────────────────────────────────────────────────────

async def launch(session: Session):
    """
    Submit the agent to the thread pool.
    Ensures only one run per session at a time using run_lock.
    """
    if session.run_lock.locked():
        # Already running, just let the new subscriber pick up the existing stream
        return

    async with session.run_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _run_agent_thread, session, loop)


async def sse_generator(session: Session):
    """
    Async generator that subscribes to the session's broadcast system.
    """
    q = session.subscribe()
    timeout_seconds = 300 

    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                yield _fmt({"type": "error", "data": {"message": "Session timed out"}})
                break

            yield _fmt(event)

            if event.get("type") in ("done", "error"):
                break
    finally:
        session.unsubscribe(q)


def _fmt(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
