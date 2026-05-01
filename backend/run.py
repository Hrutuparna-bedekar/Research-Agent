import uvicorn
import os
import sys
from pathlib import Path

# Resolve the repo root regardless of where this script is invoked from.
# Works both when called as:
#   python backend/run.py          (Render — from repo root)
#   python run.py                  (local — from backend/ dir)
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT   = BACKEND_DIR.parent

# Put repo root first so agent.py, state.py, config.py are importable
sys.path.insert(0, str(REPO_ROOT))
# Put backend dir second so main.py, router.py etc. are importable
sys.path.insert(0, str(BACKEND_DIR))

# Change CWD to repo root so relative paths like "data/" resolve correctly
os.chdir(REPO_ROOT)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
