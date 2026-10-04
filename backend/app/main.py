from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import coaching, demo, health, sensor
from app.sensors import SensorRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("motion_coach")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own exactly one live BLE sensor runtime for the whole process."""
    settings = get_settings()
    if settings.sensor_enabled:
        logger.info("Starting live IMU sensor runtime")
        await app.state.sensor.start()
    else:
        logger.info("Live IMU sensor disabled (set SENSOR_ENABLED=true to enable)")
    try:
        yield
    finally:
        await app.state.sensor.stop()


app = FastAPI(title="Motion Coach API", version="0.1.0", lifespan=lifespan)

# Created eagerly so routes always have a runtime, even if lifespan does not run
# (e.g. plain TestClient) or the sensor is disabled.
_settings = get_settings()
app.state.sensor = SensorRuntime(
    device_name=_settings.sensor_device_name,
    buffer_seconds=_settings.sensor_buffer_seconds,
    retry_delay=_settings.sensor_retry_delay,
)

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
app.include_router(sensor.router)


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
