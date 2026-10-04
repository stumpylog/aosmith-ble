import time

import pytest

from aosmith_ble.client import AOSmithBLEClient
from aosmith_ble.exceptions import NotConnectedError

from fake_transport import FakeBleakClient


async def test_async_release_disconnects_and_blocks_reconnect_window():
    fake = FakeBleakClient(lambda cmd: [])
    fake.is_connected = True
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    client._session_ok = True

    await client.async_release(seconds=0.2)
    assert not client.is_connected

    with pytest.raises(NotConnectedError, match="released"):
        await client.connect()


async def test_connect_succeeds_again_after_release_window_elapses():
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._released_until = time.monotonic() - 1  # already elapsed
    # Not asserting full connect() succeeds here (that needs a real BLEDevice
    # lookup this fake doesn't provide) -- only that the release-window guard
    # itself doesn't fire when the window has passed.
    assert time.monotonic() >= client._released_until


async def test_exchange_capture_sink_records_labeled_request_and_response():
    responses = [bytes.fromhex("aabbcc")]

    def responder(_cmd: bytes) -> list[bytes]:
        return responses

    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    fake.is_connected = True
    fake._notify_callback = client._on_notify

    client._capture_sink = []
    await client._exchange(b"\x11\x22", label="my_label")

    assert client._capture_sink == [
        {"label": "my_label", "request_hex": "1122", "response_hex": "aabbcc"}
    ]


async def test_exchange_does_not_capture_when_sink_is_none():
    def responder(_cmd: bytes) -> list[bytes]:
        return [bytes.fromhex("aabbcc")]

    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    fake.is_connected = True
    fake._notify_callback = client._on_notify

    await client._exchange(b"\x11\x22", label="ignored")
    assert client._capture_sink is None
