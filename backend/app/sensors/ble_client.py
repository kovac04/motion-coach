"""Async BLE client for the Motion Coach wearable (Mac = BLE central).

Uses bleak. Deliberately decoupled from Jev/Gemini/ElevenLabs: this layer only
produces ImuSample values.

This module imports bleak lazily-friendly (bleak is a runtime dependency), but
the packet decoding is separate in `packet.py` so tests never need BLE hardware.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from .packet import ImuSample, decode_packet

logger = logging.getLogger(__name__)

DEVICE_NAME = "MotionCoach-IMU"
MOTION_SERVICE_UUID = "8a1f0001-6b2e-4c3d-9e5f-0a1b2c3d4e5f"
IMU_DATA_CHARACTERISTIC_UUID = "8a1f0002-6b2e-4c3d-9e5f-0a1b2c3d4e5f"
CONTROL_CHARACTERISTIC_UUID = "8a1f0003-6b2e-4c3d-9e5f-0a1b2c3d4e5f"


class DeviceNotFoundError(RuntimeError):
    pass


class BleImuClient:
    def __init__(
        self,
        device_name: str = DEVICE_NAME,
        service_uuid: str = MOTION_SERVICE_UUID,
        data_uuid: str = IMU_DATA_CHARACTERISTIC_UUID,
        control_uuid: str = CONTROL_CHARACTERISTIC_UUID,
        scan_timeout: float = 10.0,
    ) -> None:
        self.device_name = device_name
        self.service_uuid = service_uuid.lower()
        self.data_uuid = data_uuid
        self.control_uuid = control_uuid
        self.scan_timeout = scan_timeout
        self.address: str | None = None
        self.malformed = 0

    async def find_device(self):
        from bleak import BleakScanner

        def match(device, advertisement) -> bool:
            service_uuids = [u.lower() for u in (advertisement.service_uuids or [])]
            if self.service_uuid in service_uuids:
                return True
            return advertisement.local_name == self.device_name

        device = await BleakScanner.find_device_by_filter(match, timeout=self.scan_timeout)
        if device is None:
            raise DeviceNotFoundError(
                f"no BLE device advertising {self.service_uuid} or named {self.device_name!r}"
            )
        return device

    async def stream(self) -> AsyncIterator[ImuSample]:
        """Connect and yield decoded samples until disconnected."""
        from bleak import BleakClient

        device = await self.find_device()
        self.address = getattr(device, "address", str(device))
        logger.info("connecting to %s (%s)", self.device_name, self.address)

        queue: asyncio.Queue[ImuSample] = asyncio.Queue(maxsize=4096)

        def handler(_sender, data: bytearray) -> None:
            try:
                sample = decode_packet(bytes(data), host_timestamp=time.monotonic())
            except ValueError:
                self.malformed += 1
                return
            if queue.full():
                # Drop oldest so a slow consumer cannot stall notifications.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(sample)

        async with BleakClient(device) as client:
            await client.start_notify(self.data_uuid, handler)
            logger.info("notifications started")
            try:
                while client.is_connected:
                    try:
                        yield await asyncio.wait_for(queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
            finally:
                try:
                    await client.stop_notify(self.data_uuid)
                except Exception:  # noqa: BLE001 - best effort on teardown
                    pass

    async def send_control(self, command: str) -> None:
        """Send START / STOP / PING to the control characteristic."""
        from bleak import BleakClient

        device = await self.find_device()
        async with BleakClient(device) as client:
            await client.write_gatt_char(self.control_uuid, command.encode("ascii"), response=False)
