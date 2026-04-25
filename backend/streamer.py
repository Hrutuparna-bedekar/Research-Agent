
import asyncio
import json
import sys
import os
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
    and puts it on the session queue via the event loop.
    """
    def put(event: dict):
        loop.call_soon_threadsafe(session.queue.put_nowait, event)

    try:
        wf = _get_wf()
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

                # Node started (emit before processing)
                put({
                    "type": "node_start",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "data": {},
                })

                # Special handling: stream report or chat response token by token
                if (node_name in ("generate_report", "chat_response")) and "final_output" in node_output:
                    report_text = node_output["final_output"]
                    session.report = report_text
                    # Simulate token chunks (split by words for smooth UX)
                    words = report_text.split(" ")
                    chunk_size = 5
                    for i in range(0, len(words), chunk_size):
                        chunk_text = " ".join(words[i:i+chunk_size]) + " "
                        put({
                            "type": "report_chunk",
                            "node": node_name,
                            "data": {"chunk": chunk_text},
                        })

                # Update session metadata from reflect node
                if node_name == "reflect":
                    session.confidence  = node_output.get("confidence", 0)
                    session.plan_steps  = node_output.get("plan_step_index", 0)
                    session.gap_passes  = node_output.get("gap_step_index", 0)

                # Node done
                put({
                    "type": "node_done",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "data": _node_summary(node_name, node_output),
                })

        session.status = "done"
        import datetime
        session.finished_at = datetime.datetime.utcnow()
        session_manager.update(session)
        put({"type": "done", "node": None, "data": {"session_id": session.session_id}})

    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        session_manager.update(session)
        put({"type": "error", "node": None, "data": {"message": str(exc)}})


# ── public API ────────────────────────────────────────────────────────────────

def launch(session: Session):
    """
    Submit the agent to the thread pool.
    Returns immediately — the SSE stream will drain the queue.
    """
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_agent_thread, session, loop)


async def sse_generator(session: Session):
    """
    Async generator that drains the session queue and yields
    properly formatted text/event-stream lines.
    """
    SENTINEL = object()
    timeout_seconds = 300  # 5-minute max per session

    while True:
        try:
            event = await asyncio.wait_for(session.queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            yield _fmt({"type": "error", "data": {"message": "Session timed out"}})
            break

        yield _fmt(event)

        if event.get("type") in ("done", "error"):
            break


def _fmt(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
