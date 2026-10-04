from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.sensors import SensorRuntime

router = APIRouter(prefix="/api/sensor", tags=["sensor"])

# How much recent history the live chart receives, and how often.
STREAM_WINDOW_SECONDS = 2.5
STREAM_INTERVAL_SECONDS = 0.1


def _runtime(request: Request) -> SensorRuntime:
    return request.app.state.sensor


@router.get("/status")
def sensor_status(request: Request) -> dict:
    return _runtime(request).status()


@router.websocket("/stream")
async def sensor_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime: SensorRuntime = websocket.app.state.sensor
    try:
        while True:
            samples = runtime.recent(STREAM_WINDOW_SECONDS)
            await websocket.send_json(
                {
                    "type": "sensor",
                    "status": runtime.status(),
                    "samples": [
                        [
                            round(sample.host_timestamp or 0.0, 3),
                            round(sample.gyro_magnitude, 1),
                            round(sample.accel_magnitude, 1),
                        ]
                        for sample in samples
                    ],
                }
            )
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 - never let a client kill the server
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
