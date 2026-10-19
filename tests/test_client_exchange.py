"""The request/reply exchange: one pending request, answered only by a reply
that matches it, and ended at once when the link goes away."""

from __future__ import annotations

import asyncio
import logging

import pytest

from aosmith_ble import protocol as p
from aosmith_ble.exceptions import NotConnectedError, ProtocolError
from test_client_writes import _client_with_matched_profile, _read_response

BLOCK11_READ = p.read_request(11, 0, 20)
BLOCK11_REPLY = _read_response(11, 0, bytes(range(40)))
BLOCK27_READ = p.read_request(27, 6, 4)
BLOCK27_REPLY = _read_response(27, 6, bytes(8))
WRITE_ACK_MODE = bytes.fromhex("db02070b0f80fa")


async def test_a_late_reply_is_not_taken_for_the_next_read():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == BLOCK11_READ:
            return [BLOCK27_REPLY, BLOCK11_REPLY]  # the Block 27 reply is late
        return []

    client = _client_with_matched_profile(responder)
    client._timeout = 0.05
    with pytest.raises(ProtocolError, match="no response"):
        await client._raw_read(27, 6, 4)
    assert await client._raw_read(11, 0, 20) == bytes(range(40))


async def test_an_unrelated_frame_is_dropped_and_logged(caplog):
    client = _client_with_matched_profile(
        lambda cmd: [WRITE_ACK_MODE, BLOCK11_REPLY] if cmd == BLOCK11_READ else []
    )
    with caplog.at_level(logging.DEBUG, logger="aosmith_ble.client"):
        assert await client._raw_read(11, 0, 20) == bytes(range(40))
    assert any("dropping" in r.getMessage() for r in caplog.records)
    assert not any(WRITE_ACK_MODE.hex() in r.getMessage() for r in caplog.records)


async def test_a_second_concurrent_exchange_is_refused():
    client = _client_with_matched_profile(lambda cmd: [])
    client._timeout = 5.0
    first = asyncio.create_task(client._raw_read(11, 0, 20))
    await asyncio.sleep(0)
    try:
        with pytest.raises(ProtocolError, match="in flight"):
            await client._exchange(p.read_request(2, 7, 1))
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first


async def test_a_failed_send_becomes_not_connected():
    client = _client_with_matched_profile(lambda cmd: [])

    async def broken_write(_char, _data, response=True):
        raise RuntimeError("gone")

    client._client.write_gatt_char = broken_write
    with pytest.raises(NotConnectedError) as excinfo:
        await client._raw_read(11, 0, 20)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert client._pending is None


async def test_pending_is_cleared_after_a_timeout():
    client = _client_with_matched_profile(lambda cmd: [])
    client._timeout = 0.05
    with pytest.raises(ProtocolError):
        await client._raw_read(11, 0, 20)
    assert client._pending is None


async def test_a_frame_with_nothing_pending_is_dropped():
    client = _client_with_matched_profile(
        lambda cmd: [BLOCK11_REPLY] if cmd == BLOCK11_READ else []
    )
    client._on_notify(None, bytearray(BLOCK27_REPLY))
    assert await client._raw_read(11, 0, 20) == bytes(range(40))


async def test_reply_delivered_during_the_write_is_matched():
    client = _client_with_matched_profile(
        lambda cmd: [BLOCK11_REPLY] if cmd == BLOCK11_READ else []
    )
    assert await client._raw_read(11, 0, 20) == bytes(range(40))
    assert client._pending is None


def _drops_the_link_on(client, request: bytes):
    """A responder that loses the link the moment `request` is sent."""

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == request:
            client._client.is_connected = False
            client._on_link_lost(client._client)
        return []

    return responder


async def test_link_loss_fails_the_read_in_flight_at_once():
    client = _client_with_matched_profile(lambda cmd: [])
    fired: list[int] = []
    client._on_disconnect = lambda: fired.append(1)
    client._client._responder = _drops_the_link_on(client, BLOCK11_READ)
    client._timeout = 5.0
    with pytest.raises(NotConnectedError, match="link was lost"):
        await asyncio.wait_for(client._raw_read(11, 0, 20), 1.0)
    assert fired == [1]
    assert client._session_ok is False


async def test_link_loss_without_a_host_hook_still_fails_the_exchange():
    client = _client_with_matched_profile(lambda cmd: [])
    client._client._responder = _drops_the_link_on(client, BLOCK11_READ)
    client._timeout = 5.0
    with pytest.raises(NotConnectedError, match="link was lost"):
        await asyncio.wait_for(client._raw_read(11, 0, 20), 1.0)


async def test_a_stale_links_callback_fails_nothing():
    client = _client_with_matched_profile(lambda cmd: [])

    def responder(cmd: bytes) -> list[bytes]:
        client._on_link_lost(object())
        return [BLOCK11_REPLY] if cmd == BLOCK11_READ else []

    client._client._responder = responder
    assert await client._raw_read(11, 0, 20) == bytes(range(40))
    assert client._session_ok is True


async def test_disconnect_fails_the_exchange_in_flight():
    client = _client_with_matched_profile(lambda cmd: [])
    client._timeout = 5.0
    read = asyncio.create_task(client._raw_read(11, 0, 20))
    await asyncio.sleep(0)
    await client.disconnect()
    with pytest.raises(NotConnectedError, match="closed"):
        await asyncio.wait_for(read, 1.0)


async def test_release_sets_the_window_before_closing(monkeypatch):
    import time

    client = _client_with_matched_profile(lambda cmd: [])
    seen: list[bool] = []

    async def recording_disconnect():
        seen.append(client._released_until > time.monotonic())

    monkeypatch.setattr(client, "disconnect", recording_disconnect)
    await client.async_release(60)
    assert seen == [True]


async def test_a_new_exchange_after_a_drop_is_unaffected():
    from fake_transport import FakeBleakClient

    client = _client_with_matched_profile(lambda cmd: [])
    client._client._responder = _drops_the_link_on(client, BLOCK11_READ)
    with pytest.raises(NotConnectedError):
        await asyncio.wait_for(client._raw_read(11, 0, 20), 1.0)

    fresh = FakeBleakClient(lambda cmd: [BLOCK11_REPLY] if cmd == BLOCK11_READ else [])
    fresh.is_connected = True
    fresh._notify_callback = client._on_notify
    client._client = fresh
    assert await client._raw_read(11, 0, 20) == bytes(range(40))
