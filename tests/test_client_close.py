"""Tests for AOSmithBLEClient.async_close(): a permanent, lock-respecting
shutdown, unlike disconnect() which leaves the client reusable."""

from __future__ import annotations

import asyncio

import bleak_retry_connector
import pytest

from aosmith_ble import AOSmithBLEClient, NotConnectedError
from aosmith_ble import client as client_mod
from fake_transport import FakeBleakClient
from test_client_hooks import patch_establish
from test_client_session import _full_happy_path_responder


async def _connected(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    await client.connect()
    return client, fake, calls


async def test_close_closes_the_link(monkeypatch):
    client, fake, _calls = await _connected(monkeypatch)

    await client.async_close()

    assert fake.is_connected is False
    assert client.is_connected is False


async def test_connect_after_close_raises_and_does_not_reconnect(monkeypatch):
    client, _fake, calls = await _connected(monkeypatch)
    await client.async_close()

    with pytest.raises(NotConnectedError, match="closed"):
        await client.connect()

    assert len(calls) == 1  # only the original connect


async def test_operations_after_close_raise_without_touching_the_link(monkeypatch):
    client, fake, calls = await _connected(monkeypatch)
    await client.async_close()
    written_before = len(fake.written)

    with pytest.raises(NotConnectedError, match="closed"):
        await client.async_get_state()
    with pytest.raises(NotConnectedError, match="closed"):
        await client.async_set_setpoint(120.0)
    with pytest.raises(NotConnectedError, match="closed"):
        await client.async_diagnose()

    assert len(calls) == 1
    assert len(fake.written) == written_before


async def test_close_is_idempotent(monkeypatch):
    client, _fake, _calls = await _connected(monkeypatch)

    await client.async_close()
    await client.async_close()


async def test_close_on_a_client_that_never_connected():
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")

    await client.async_close()

    with pytest.raises(NotConnectedError, match="closed"):
        await client.connect()


async def test_close_waits_for_an_in_flight_operation(monkeypatch):
    client, fake, _calls = await _connected(monkeypatch)

    await client._lock.acquire()  # stand in for a read or write in flight
    closing = asyncio.create_task(client.async_close())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert closing.done() is False
    assert fake.is_connected is True  # the link is not pulled from under it
    # ...but nothing new may start: the closed flag is already set.
    with pytest.raises(NotConnectedError, match="closed"):
        await client.connect()

    client._lock.release()
    await closing

    assert fake.is_connected is False


async def test_close_cancelled_by_a_timeout_still_blocks_reconnect(monkeypatch):
    client, fake, calls = await _connected(monkeypatch)

    await client._lock.acquire()  # an operation that never finishes
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.async_close(), timeout=0.05)
    client._lock.release()

    # The caller's documented fallback after a close timeout.
    await client.disconnect()

    with pytest.raises(NotConnectedError, match="closed"):
        await client.connect()
    assert len(calls) == 1
    assert fake.is_connected is False


async def test_close_during_establish_leaves_no_live_link(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    gate = asyncio.Event()

    async def gated_establish(cls, device, name, **kwargs):
        await gate.wait()
        await fake.connect()
        return fake

    monkeypatch.setattr(bleak_retry_connector, "establish_connection", gated_establish)
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")

    connecting = asyncio.create_task(client.connect())
    await asyncio.sleep(0.01)
    await client.async_close()  # lands while connect() is mid-establish
    gate.set()

    with pytest.raises(NotConnectedError, match="closed"):
        await connecting
    assert fake.is_connected is False
    assert client._client is None


async def test_close_during_link_setup_raises_not_connected(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    patch_establish(monkeypatch, fake)
    gate = asyncio.Event()
    entered = asyncio.Event()
    real_start_notify = fake.start_notify

    async def gated_start_notify(char_uuid, callback):
        entered.set()
        await gate.wait()
        await real_start_notify(char_uuid, callback)

    fake.start_notify = gated_start_notify
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")

    connecting = asyncio.create_task(client.connect())
    await entered.wait()
    await client.async_close()  # the link exists but the session does not
    gate.set()

    with pytest.raises(NotConnectedError, match="closed"):
        await connecting
    assert fake.is_connected is False


async def test_operations_queued_before_close_do_not_run(monkeypatch):
    client, fake, _calls = await _connected(monkeypatch)
    written_before = len(fake.written)

    await client._lock.acquire()
    state = asyncio.create_task(client.async_get_state())
    diagnose = asyncio.create_task(client.async_diagnose())
    await asyncio.sleep(0)
    closing = asyncio.create_task(client.async_close())
    await asyncio.sleep(0)
    client._lock.release()

    await closing
    for task in (state, diagnose):
        with pytest.raises(NotConnectedError, match="closed"):
            await task
    assert len(fake.written) == written_before
    assert fake.is_connected is False


async def test_cancelled_close_still_finishes_closing_the_link(monkeypatch):
    client, fake, _calls = await _connected(monkeypatch)
    release = asyncio.Event()
    real_disconnect = fake.disconnect

    async def slow_disconnect():
        await release.wait()
        await real_disconnect()

    fake.disconnect = slow_disconnect

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.async_close(), timeout=0.05)
    assert fake.is_connected is True  # still closing
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)

    assert fake.is_connected is False
