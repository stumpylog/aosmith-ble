"""Tests for the optional embedding hooks on AOSmithBLEClient.

These drive the real `connect()` against a fake `establish_connection` that
records what it was called with, so each test can assert on the arguments
the client handed to bleak-retry-connector.
"""

from __future__ import annotations

import bleak_retry_connector
import pytest
from bleak import BleakClient

from aosmith_ble import AOSmithBLEClient
from aosmith_ble import client as client_mod
from fake_transport import FakeBleakClient
from test_client_session import _full_happy_path_responder


def patch_establish(monkeypatch, fake):
    """Replace establish_connection; return the list of recorded calls."""
    calls: list[dict] = []

    async def fake_establish_connection(cls, device, name, **kwargs):
        calls.append({"cls": cls, "device": device, "name": name, "kwargs": kwargs})
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    return calls


async def test_defaults_pass_bleak_client_and_no_extra_keywords(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    device = object()
    client = AOSmithBLEClient(device=device, pairing_code=b"123456")
    await client.connect()

    assert len(calls) == 1
    assert calls[0]["cls"] is BleakClient
    assert calls[0]["device"] is device
    assert calls[0]["kwargs"] == {}


async def test_client_class_is_passed_through(monkeypatch):
    class MyClient(BleakClient):
        pass

    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    client = AOSmithBLEClient(
        device=object(), pairing_code=b"123456", client_class=MyClient
    )
    await client.connect()

    assert calls[0]["cls"] is MyClient


async def test_resolver_supplies_the_device_on_each_connect(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    first, second = object(), object()
    handles = iter([first, second])
    client = AOSmithBLEClient(
        device=object(), pairing_code=b"123456", device_resolver=lambda: next(handles)
    )

    await client.connect()
    await client.disconnect()
    await client.connect()

    assert [c["device"] for c in calls] == [first, second]


async def test_resolver_is_handed_to_establish_connection_as_callback(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    handles = iter([object(), object()])
    client = AOSmithBLEClient(
        device=object(), pairing_code=b"123456", device_resolver=lambda: next(handles)
    )
    await client.connect()

    # The connector's retry callback asks the resolver again.
    newer = calls[0]["kwargs"]["ble_device_callback"]()
    assert newer is not calls[0]["device"]


async def test_resolver_returning_none_keeps_the_last_known_device(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    initial, resolved = object(), object()
    answers = iter([resolved, None, None])
    client = AOSmithBLEClient(
        device=initial, pairing_code=b"123456", device_resolver=lambda: next(answers)
    )

    await client.connect()
    await client.disconnect()
    await client.connect()

    # Second connect: the resolver had nothing new, so the previously
    # resolved handle is reused, not the constructor's.
    assert [c["device"] for c in calls] == [resolved, resolved]
    # The retry callback also falls back instead of returning None.
    assert calls[1]["kwargs"]["ble_device_callback"]() is resolved


async def test_resolver_that_raises_leaves_no_link(monkeypatch):
    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    def boom():
        raise RuntimeError("lookup failed")

    client = AOSmithBLEClient(
        device=object(), pairing_code=b"123456", device_resolver=boom
    )
    with pytest.raises(RuntimeError, match="lookup failed"):
        await client.connect()

    assert calls == []
    assert client._client is None
    assert client.is_connected is False
