"""A write that is not acknowledged with 0x80 is settled by reading the value
back, never by sending it again. A 0x40 refusal is final and is not read
back. The readback decides: the value is there -> success with a warning;
it is not, or cannot be read -> WriteUnconfirmedError."""

from __future__ import annotations

import asyncio
import logging

import pytest

import aosmith_ble.crc as crc_mod
from aosmith_ble import WriteUnconfirmedError
from aosmith_ble import protocol as p
from aosmith_ble.const import Mode
from aosmith_ble.exceptions import NotConnectedError, ProtocolError
from fake_transport import FakeBleakClient
from test_client_writes import (
    _block27_reply,
    _client_with_matched_profile,
    _healthy_state_responses,
    _is_block27_read,
    _read_response,
)

WRITE = p.set_setpoint_request(120.0)
NEW = int.from_bytes(WRITE[5:7], "big")
OLD = 0x331C  # the setpoint the healthy Block 11 state reply carries
READBACK = p.read_request(11, 0, 1)
WRITE_ACK = bytes.fromhex("db02070b008050")


def _stub(block: int, start: int, status: int) -> bytes:
    return crc_mod.frame(bytes([0xDB, 0x02, 0x07, block, start, status]))


def _word_reply(word: int, start: int = 0) -> bytes:
    return _read_response(11, start, word.to_bytes(2, "big"))


class Heater:
    """Serves healthy state reads; answers the write with `on_write` and each
    readback with the next entry of `readbacks` (silence once they run out)."""

    def __init__(
        self,
        on_write: list[bytes] | None = None,
        readbacks: list[list[bytes]] | None = None,
        write: bytes = WRITE,
        readback: bytes = READBACK,
    ):
        self.on_write = on_write or []
        self.readbacks = list(readbacks or [])
        self.write = write
        self.readback = readback
        self.state = _healthy_state_responses()

    def __call__(self, cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [self.state["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [self.state["fault"]]
        if _is_block27_read(cmd):
            return [_block27_reply(cmd)]
        if cmd == self.write:
            return self.on_write
        if cmd == self.readback and self.readbacks:
            return self.readbacks.pop(0)
        return []


def _client(heater: Heater):
    client = _client_with_matched_profile(heater)
    client._timeout = 0.05
    return client


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _reattaching_connect(client, heater: Heater, calls: list[FakeBleakClient]):
    async def connect():
        fresh = FakeBleakClient(heater)
        fresh.is_connected = True
        fresh._notify_callback = client._on_notify
        client._client = fresh
        client._session_ok = True
        calls.append(fresh)

    return connect


def _drop_link_on_write(client):
    def drop(_cmd):
        client._client.is_connected = False
        client._on_link_lost(client._client)
        return []

    return drop


async def test_unacknowledged_write_that_applied_succeeds_with_a_warning(caplog):
    client = _client(Heater(readbacks=[[_word_reply(NEW)]]))
    with caplog.at_level(logging.WARNING, logger="aosmith_ble.client"):
        await client.async_set_setpoint(120.0)
    assert len(_warnings(caplog)) == 1
    assert "not acknowledged" in _warnings(caplog)[0]
    assert client._client.written.count(WRITE) == 1


async def test_unacknowledged_write_that_did_not_apply_raises():
    client = _client(Heater(readbacks=[[_word_reply(OLD)]]))
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await client.async_set_setpoint(120.0)
    err = excinfo.value
    assert isinstance(err, ProtocolError)
    assert (err.block, err.param, err.expected, err.actual) == (11, 0, (NEW,), (OLD,))
    assert client._client.written.count(WRITE) == 1


async def test_readback_failure_raises_with_no_actual():
    client = _client(Heater())
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await client.async_set_setpoint(120.0)
    assert excinfo.value.actual is None
    assert isinstance(excinfo.value.__cause__, ProtocolError)
    assert client._client.written.count(WRITE) == 1


async def test_refused_write_raises_without_a_readback():
    client = _client(Heater(on_write=[_stub(11, 0, 0x40)]))
    with pytest.raises(ProtocolError, match="write rejected") as excinfo:
        await client.async_set_setpoint(120.0)
    assert not isinstance(excinfo.value, WriteUnconfirmedError)
    assert READBACK not in client._client.written
    assert client._client.written.count(WRITE) == 1


async def test_unknown_status_is_settled_by_readback(caplog):
    client = _client(
        Heater(on_write=[_stub(11, 0, 0x01)], readbacks=[[_word_reply(NEW)]])
    )
    with caplog.at_level(logging.WARNING, logger="aosmith_ble.client"):
        await client.async_set_setpoint(120.0)
    assert any("0x01" in m for m in _warnings(caplog))
    assert client._client.written.count(WRITE) == 1


async def test_expired_write_ack_recovers_and_reads_back(monkeypatch):
    client = _client(
        Heater(on_write=[_stub(11, 0, 0x10)], readbacks=[[_word_reply(NEW)]])
    )
    recoveries: list[int] = []

    async def recover():
        recoveries.append(1)
        client._session_ok = True

    monkeypatch.setattr(client, "_recover_session", recover)
    await client.async_set_setpoint(120.0)
    assert recoveries == [1]
    assert client._client.written.count(WRITE) == 1


async def test_link_lost_before_the_ack_reconnects_and_reads_back(monkeypatch):
    heater = Heater(readbacks=[[_word_reply(NEW)]])
    client = _client(heater)
    first = client._client
    heater.on_write = []
    first._responder = lambda cmd: (
        _drop_link_on_write(client)(cmd) if cmd == WRITE else heater(cmd)
    )
    links: list[FakeBleakClient] = []
    monkeypatch.setattr(client, "connect", _reattaching_connect(client, heater, links))

    await client.async_set_setpoint(120.0)
    assert len(links) == 1
    assert first.written.count(WRITE) + links[0].written.count(WRITE) == 1


async def test_failed_send_is_settled_by_readback(caplog):
    client = _client(Heater(readbacks=[[_word_reply(NEW)]]))
    fake = client._client
    send = fake.write_gatt_char

    async def flaky(char, data, response=True):
        if bytes(data) == WRITE:
            raise RuntimeError("gone")
        await send(char, data, response)

    fake.write_gatt_char = flaky
    with caplog.at_level(logging.WARNING, logger="aosmith_ble.client"):
        await client.async_set_setpoint(120.0)
    assert len(_warnings(caplog)) == 1
    assert WRITE not in fake.written  # the failed send, never repeated


async def test_reconnect_failure_raises_with_no_actual(monkeypatch):
    heater = Heater()
    client = _client(heater)
    client._client._responder = lambda cmd: (
        _drop_link_on_write(client)(cmd) if cmd == WRITE else heater(cmd)
    )

    async def failing_connect():
        raise RuntimeError("no adapter")

    monkeypatch.setattr(client, "connect", failing_connect)
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await client.async_set_setpoint(120.0)
    assert excinfo.value.actual is None
    assert isinstance(excinfo.value.__cause__, RuntimeError)


async def test_release_during_an_unacked_write_opens_no_link(monkeypatch):
    client = _client(Heater())
    client._timeout = 5.0
    fake = client._client
    connects: list[int] = []

    async def recording_connect():
        connects.append(1)

    monkeypatch.setattr(client, "connect", recording_connect)
    write = asyncio.create_task(client.async_set_setpoint(120.0))
    while WRITE not in fake.written:
        await asyncio.sleep(0)
    await client.async_release(60)
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await asyncio.wait_for(write, 1.0)
    assert excinfo.value.actual is None
    assert connects == []


async def test_late_frames_during_readback_are_ignored():
    stale_poll = _healthy_state_responses()["block11"]  # 20 words, OLD at word 0
    client = _client(Heater(readbacks=[[WRITE_ACK, stale_poll, _word_reply(NEW)]]))
    await client.async_set_setpoint(120.0)


async def test_session_expired_readback_recovers_once(monkeypatch):
    client = _client(Heater(readbacks=[[_stub(11, 0, 0x10)], [_word_reply(NEW)]]))
    recoveries: list[int] = []

    async def recover():
        recoveries.append(1)

    monkeypatch.setattr(client, "_recover_session", recover)
    await client.async_set_setpoint(120.0)
    assert recoveries == [1]


async def test_unacknowledged_mode_write_that_applied_succeeds(caplog):
    write = p.set_mode_request(int(Mode.HEAT_PUMP), 0)
    word = int(Mode.HEAT_PUMP)
    client = _client(
        Heater(
            write=write,
            readback=p.read_request(11, 15, 1),
            readbacks=[[_word_reply(word, start=15)]],
        )
    )
    with caplog.at_level(logging.WARNING, logger="aosmith_ble.client"):
        await client.async_set_mode(Mode.HEAT_PUMP)
    assert len(_warnings(caplog)) == 1
    assert client._client.written.count(write) == 1


async def test_write_on_a_dead_link_is_not_sent():
    """Regression guard: nothing was sent, so there is nothing to settle."""
    heater = Heater()
    client = _client(heater)

    def responder(cmd: bytes) -> list[bytes]:
        if _is_block27_read(cmd):  # the last state read before the write
            client._client.is_connected = False
        return heater(cmd)

    client._client._responder = responder
    with pytest.raises(NotConnectedError) as excinfo:
        await client.async_set_setpoint(120.0)
    assert not isinstance(excinfo.value, WriteUnconfirmedError)
    assert WRITE not in client._client.written


async def test_disconnect_during_the_send_opens_no_link(monkeypatch):
    client = _client(Heater())
    fake = client._client
    send = fake.write_gatt_char
    connects: list[int] = []

    async def closing_send(char, data, response=True):
        if bytes(data) == WRITE:
            await client.disconnect()  # the caller closes while the write waits
            raise RuntimeError("disconnected")
        await send(char, data, response)

    async def recording_connect():
        connects.append(1)

    fake.write_gatt_char = closing_send
    monkeypatch.setattr(client, "connect", recording_connect)
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await client.async_set_setpoint(120.0)
    assert excinfo.value.actual is None
    assert connects == []


async def test_disconnect_during_session_recovery_opens_no_link(monkeypatch):
    from aosmith_ble import client as client_mod

    client = _client(Heater(on_write=[_stub(11, 0, 0x10)]))
    connects: list[int] = []

    async def closed_mid_handshake():
        raise client_mod._LinkClosedError("the link was closed while waiting")

    async def recording_connect():
        connects.append(1)

    monkeypatch.setattr(client, "_establish_session", closed_mid_handshake)
    monkeypatch.setattr(client, "connect", recording_connect)
    with pytest.raises(WriteUnconfirmedError) as excinfo:
        await client.async_set_setpoint(120.0)
    assert excinfo.value.actual is None
    assert connects == []


async def test_a_corrupted_ack_is_settled_by_readback(caplog):
    bad_crc = WRITE_ACK[:-1] + bytes([WRITE_ACK[-1] ^ 0xFF])
    client = _client(Heater(on_write=[bad_crc], readbacks=[[_word_reply(NEW)]]))
    with caplog.at_level(logging.WARNING, logger="aosmith_ble.client"):
        await client.async_set_setpoint(120.0)
    assert any("malformed" in m for m in _warnings(caplog))
    assert client._client.written.count(WRITE) == 1
