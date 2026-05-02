import asyncio
import uuid
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sessions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            query TEXT,
            status TEXT,
            report TEXT,
            confidence REAL,
            started_at TEXT,
            finished_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Session:
    def __init__(self, session_id: str, query: str):
        self.session_id  = session_id
        self.query       = query
        self.thread_id   = session_id          
        self.status      = "pending"
        self.queue: asyncio.Queue = asyncio.Queue()
        self.report      = ""
        self.confidence  = 0.0
        self.started_at  = datetime.utcnow()
        self.finished_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "session_id":  self.session_id,
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

    def create(self, query: str, session_id: Optional[str] = None) -> Session:
        sid = session_id or str(uuid.uuid4())[:8]
        
       
        if sid in self._active_sessions:
            session = self._active_sessions[sid]
            session.query = query 
            session.status = "pending"
            session.queue = asyncio.Queue()
            return session

        session = Session(sid, query)
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
            s = Session(row[0], row[1])
            s.status = row[2]
            s.report = row[3]
            s.confidence = row[4]
            s.started_at = datetime.fromisoformat(row[5])
            if row[6]: s.finished_at = datetime.fromisoformat(row[6])
            self._active_sessions[session_id] = s
            return s
        return None

    def all(self) -> List[Dict]:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT session_id, query, status, confidence, started_at, finished_at, report FROM sessions ORDER BY started_at DESC").fetchall()
        conn.close()
        
        return [
            {
                "session_id": r[0],
                "query": r[1],
                "status": r[2],
                "confidence": r[3],
                "started_at": r[4],
                "finished_at": r[5],
                "has_report": bool(r[6])
            } for r in rows
        ]

    def _save_to_db(self, session: Session):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_id, query, status, report, confidence, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session.session_id,
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
