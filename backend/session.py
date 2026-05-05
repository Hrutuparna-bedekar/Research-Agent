import asyncio
import uuid
import sqlite3
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sessions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    # Check if user_id column exists
    cursor = conn.execute("PRAGMA table_info(sessions)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if not columns:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                query TEXT,
                status TEXT,
                report TEXT,
                confidence REAL,
                started_at TEXT,
                finished_at TEXT
            )
        """)
    elif "user_id" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
        
    conn.commit()
    conn.close()

init_db()

class Session:
    def __init__(self, session_id: str, query: str, user_id: str = "default"):
        self.session_id  = session_id
        self.user_id     = user_id
        self.query       = query
        self.thread_id   = session_id          
        self.status      = "pending"
        self.report      = ""
        self.confidence  = 0.0
        self.started_at  = datetime.utcnow()
        self.finished_at: Optional[datetime] = None
        
        # Streaming state
        self._subscribers: List[asyncio.Queue] = []
        self._event_history: List[dict] = []
        self._lock = threading.Lock() # For thread-safe status/meta updates
        self.run_lock = asyncio.Lock() # To prevent concurrent agent runs

    def broadcast(self, event: dict):
        """Send an event to all active SSE subscribers and save to history."""
        if event.get("type") not in ("report_chunk"): # Don't bloat history with every tiny chunk
             self._event_history.append(event)
        
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        """Create a new queue for a subscriber and replay history."""
        q = asyncio.Queue()
        # Replay history so reconnected clients catch up
        for event in self._event_history:
            q.put_nowait(event)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def clear_run_state(self):
        """Prepare for a new agent run."""
        self._event_history = []
        self.status = "pending"
        self.report = ""

    def to_dict(self) -> dict:
        return {
            "session_id":  self.session_id,
            "user_id":     self.user_id,
            "query":       self.query,
            "status":      self.status,
            "confidence":  self.confidence,
            "started_at":  self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "has_report":  bool(self.report),
        }

class SessionManager:
    def __init__(self):
        self._active_sessions: Dict[str, Session] = {}

    def create(self, query: str, session_id: Optional[str] = None, user_id: str = "default") -> Session:
        sid = session_id or str(uuid.uuid4())[:8]
        
       
        if sid in self._active_sessions:
            session = self._active_sessions[sid]
            session.query = query 
            session.user_id = user_id
            session.clear_run_state()
            return session

        session = Session(sid, query, user_id=user_id)
        self._active_sessions[sid] = session
        self._save_to_db(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
       
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        
       
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
        
        if row:
            # Table info: session_id(0), user_id(1), query(2), status(3), report(4), confidence(5), started_at(6), finished_at(7)
            s = Session(row[0], row[2], user_id=row[1])
            s.status = row[3]
            s.report = row[4]
            s.confidence = row[5]
            s.started_at = datetime.fromisoformat(row[6])
            if row[7]: s.finished_at = datetime.fromisoformat(row[7])
            self._active_sessions[session_id] = s
            return s
        return None

    def all(self, user_id: Optional[str] = None) -> List[Dict]:
        conn = sqlite3.connect(str(DB_PATH))
        if user_id:
            rows = conn.execute("SELECT session_id, query, status, confidence, started_at, finished_at, report, user_id FROM sessions WHERE user_id = ? ORDER BY started_at DESC", (user_id,)).fetchall()
        else:
            rows = conn.execute("SELECT session_id, query, status, confidence, started_at, finished_at, report, user_id FROM sessions ORDER BY started_at DESC").fetchall()
        conn.close()
        
        return [
            {
                "session_id": r[0],
                "query": r[1],
                "status": r[2],
                "confidence": r[3],
                "started_at": r[4],
                "finished_at": r[5],
                "has_report": bool(r[6]),
                "user_id": r[7]
            } for r in rows
        ]

    def _save_to_db(self, session: Session):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_id, user_id, query, status, report, confidence, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.session_id,
            session.user_id,
            session.query,
            session.status,
            session.report,
            session.confidence,
            session.started_at.isoformat(),
            session.finished_at.isoformat() if session.finished_at else None
        ))
        conn.commit()
        conn.close()

    def update(self, session: Session):
        self._save_to_db(session)

    def delete(self, session_id: str) -> bool:
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        success = conn.total_changes > 0
        conn.close()
        return success

session_manager = SessionManager()
