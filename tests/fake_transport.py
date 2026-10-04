"""A minimal in-memory stand-in for bleak.BleakClient.

Only implements what AOSmithBLEClient actually calls: connect/disconnect,
start_notify, write_gatt_char, mtu_size, and an is_connected flag. A test
drives it by registering a responder function that maps an outgoing command
to the bytes the device would notify back (or nothing, to simulate silence).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable


class FakeBleakClient:
    def __init__(
        self,
        responder: Callable[[bytes], list[bytes]],
        mtu_size: int = 100,
    ) -> None:
        self._responder = responder
        self.mtu_size = mtu_size
        self.is_connected = False
        self._notify_callback: Callable[[object, bytearray], None] | None = None
        self.written: list[bytes] = []

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def start_notify(self, _char_uuid: str, callback) -> None:
        self._notify_callback = callback

    async def write_gatt_char(
        self, _char_uuid: str, data: bytes, response: bool = True
    ) -> None:
        self.written.append(bytes(data))
        for notification in self._responder(bytes(data)):
            assert self._notify_callback is not None
            self._notify_callback(None, bytearray(notification))
            await asyncio.sleep(0)
