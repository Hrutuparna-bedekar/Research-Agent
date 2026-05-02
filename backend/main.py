"""
FastAPI entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import logging
from router import router

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Research Agent API",
    description="AI-powered multi-step research agent with SSE streaming",
    version="1.0.0",
)

# CORS Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")

# Regular expression to match:
# 1. Any onrender.com subdomain (production backend/frontend)
# 2. Any vercel.app subdomain (production frontend)
# 3. Localhost with any port (development)
origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https?://.*\.onrender\.com|https?://.*\.vercel\.app"
if FRONTEND_URL:
    # Escape dots for regex and allow trailing slash optional
    pattern = re.escape(FRONTEND_URL).replace(r"\-", "-")
    origin_regex += f"|{pattern}/?"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.middleware("http")
async def log_requests(request, call_next):
    if request.method == "OPTIONS":
        logger.info(f"OPTIONS request to {request.url.path} from {request.headers.get('origin')}")
        logger.info(f"Headers: {dict(request.headers)}")
    response = await call_next(request)
    return response

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
