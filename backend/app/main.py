from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import coaching, demo, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("motion_coach")

app = FastAPI(title="Motion Coach API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(demo.router)
app.include_router(coaching.router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "rid=%s %s %s -> %s %.1fms",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/")
def root() -> dict:
    settings = get_settings()
    return {"name": "Motion Coach API", "docs": "/docs", "providers": settings.provider_status()}
