from typing import Optional


from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from session import session_manager
from agent import get_thread_history
from streamer import launch, sse_generator
from exporter import to_markdown_bytes, to_pdf_bytes

router = APIRouter(prefix="/api")


# ── Models ────────────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


# ── Research endpoints ────────────────────────────────────────────────────────

@router.post("/research/start")
async def start_research(body: StartRequest):
    
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session = session_manager.create(body.query.strip(), session_id=body.session_id)
    launch(session)  # non-blocking — submits to thread pool

    return {
        "session_id": session.session_id,
        "status":     session.status,
        "query":      session.query,
    }


@router.get("/research/{session_id}/stream")
async def stream_research(session_id: str):
    """SSE endpoint — streams node events and report chunks."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return StreamingResponse(
        sse_generator(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",      
        },
    )


@router.get("/research/{session_id}/status")
async def get_status(session_id: str):
    
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.get("/research/{session_id}/history")
async def get_session_history(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    history = get_thread_history(session.thread_id)
    return {"history": history}


@router.get("/research/{session_id}/report")
async def get_report(session_id: str):
  
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "done":
        raise HTTPException(status_code=202, detail="Report not ready yet")
    return {"report": session.report, "confidence": session.confidence}



@router.get("/research/{session_id}/export/markdown")
async def export_markdown(session_id: str):
    session = session_manager.get(session_id)
    if not session or not session.report:
        raise HTTPException(status_code=404, detail="Report not available")

    data = to_markdown_bytes(session.report, session.query)
    filename = f"research_{session_id}.md"
    return StreamingResponse(
        iter([data]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/research/{session_id}/export/pdf")
async def export_pdf(session_id: str):
    session = session_manager.get(session_id)
    if not session or not session.report:
        raise HTTPException(status_code=404, detail="Report not available")

    try:
        data = to_pdf_bytes(session.report, session.query)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"research_{session_id}.pdf"
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Session management ────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    return {"sessions": session_manager.all()}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if not session_manager.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}
