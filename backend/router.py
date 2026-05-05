from typing import Optional


from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from session import session_manager
from agent import get_thread_history
from streamer import launch, sse_generator
from exporter import to_markdown_bytes, to_pdf_bytes

router = APIRouter(prefix="/api")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_session_for_user(session_id: str, user_id: Optional[str]):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # If a user_id is provided (not "default" or None), enforce ownership
    if user_id and user_id != "default" and session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")
    return session


# ── Models ────────────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None


# ── Research endpoints ────────────────────────────────────────────────────────

@router.post("/research/start")
async def start_research(body: StartRequest, x_user_id: Optional[str] = Header(None)):
    
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    user_id = body.user_id or x_user_id or "default"
    session = session_manager.create(body.query.strip(), session_id=body.session_id, user_id=user_id)
    launch(session)  # non-blocking — starts background task

    return {
        "session_id": session.session_id,
        "status":     session.status,
        "query":      session.query,
    }


@router.get("/research/{session_id}/stream")
async def stream_research(session_id: str, x_user_id: Optional[str] = Header(None), user_id: Optional[str] = Query(None)):
    """SSE endpoint — streams node events and report chunks."""
    session = get_session_for_user(session_id, x_user_id or user_id)

    return StreamingResponse(
        sse_generator(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",      
        },
    )


@router.get("/research/{session_id}/status")
async def get_status(session_id: str, x_user_id: Optional[str] = Header(None)):
    session = get_session_for_user(session_id, x_user_id)
    return session.to_dict()


@router.get("/research/{session_id}/history")
async def get_session_history(session_id: str, x_user_id: Optional[str] = Header(None)):
    session = get_session_for_user(session_id, x_user_id)
    history = get_thread_history(session.thread_id)
    return {"history": history}


@router.get("/research/{session_id}/report")
async def get_report(session_id: str, x_user_id: Optional[str] = Header(None)):
    session = get_session_for_user(session_id, x_user_id)
    if session.status != "done":
        raise HTTPException(status_code=202, detail="Report not ready yet")
    return {"report": session.report, "confidence": session.confidence}



@router.get("/research/{session_id}/export/markdown")
async def export_markdown(session_id: str, user_id: Optional[str] = Query(None)):
    session = get_session_for_user(session_id, user_id)
    if not session.report:
        raise HTTPException(status_code=404, detail="Report not available")

    data = to_markdown_bytes(session.report, session.query)
    filename = f"research_{session_id}.md"
    return StreamingResponse(
        iter([data]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/research/{session_id}/export/pdf")
async def export_pdf(session_id: str, user_id: Optional[str] = Query(None)):
    session = get_session_for_user(session_id, user_id)
    if not session.report:
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
async def list_sessions(x_user_id: Optional[str] = Header(None)):
    return {"sessions": session_manager.all(user_id=x_user_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, x_user_id: Optional[str] = Header(None)):
    # Verify ownership before deletion
    get_session_for_user(session_id, x_user_id)
    
    if not session_manager.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}
