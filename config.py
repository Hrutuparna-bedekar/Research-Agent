from pathlib import Path

MAX_PLAN_LOOPS=5
MAX_GAP_LOOPS=3
CONF_THRESHOLD=.65
DOCS_PER_STEP=6
RAG_MIN_SCORE=.4
CHECKPOINT_DB = Path(__file__).resolve().parent / "data" / "checkpoints.sqlite3"
CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
FAISS_PATH = "data/query/faiss_index"