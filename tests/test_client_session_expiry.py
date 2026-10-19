"""The heater ends its session about 29.5 minutes after it was established,
while the BLE link stays up, and answers the next request with status 0x10.

A read recovers by re-running the session handshake on the open link, then
by a full reconnect if that fails, and is retried once. A write is never
re-sent: its pre-write state read is what recovers the session, and an
expired ACK is settled by reading the value back.
"""

from __future__ import annotations

import pytest

import aosmith_ble.crc as crc_mod
from aosmith_ble import client as client_mod
from aosmith_ble import protocol as p
from aosmith_ble.const import STATUS_SESSION_EXPIRED
from aosmith_ble.exceptions import (
    SessionError,
    SessionExpiredError,
    WriteUnconfirmedError,
)
from aosmith_ble.profiles import FieldName
from fake_transport import FakeBleakClient
from test_client_hooks import patch_establish
from test_client_session import _full_happy_path_responder
from test_client_writes import (
    _block27_reply,
    _client_with_matched_profile,
    _healthy_state_responses,
    _is_block27_read,
    _read_response,
)

F1_PREFIX = bytes([0xBD, 0xF1, 0x19, 0x01])
STATE_READS = {
    p.read_request(11, 0, 20): "block11",
    p.read_request(2, 7, 1): "fault",
}


def _is_state_read(cmd: bytes) -> bool:
    return cmd in STATE_READS or _is_block27_read(cmd)


def _expired(block: int, start: int) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start, STATUS_SESSION_EXPIRED])
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def test_parse_read_raises_session_expired_on_status_0x10():
    with pytest.raises(SessionExpiredError):
        p.parse_read(
            _expired(11, 0), request_block=11, request_start=0, request_words=20
        )


def test_session_expired_is_a_session_error():
    assert issubclass(SessionExpiredError, SessionError)


class ExpiringHeater:
    """Serves the handshake and state reads; the first `expire_reads` state
    reads come back 0x10, as from a heater whose session just ended."""

    def __init__(self, expire_reads: int = 1):
        self.expire_reads = expire_reads
        self.handshakes = 0
        self._handshake = _full_happy_path_responder()
        self._state = _healthy_state_responses()

    def __call__(self, cmd: bytes) -> list[bytes]:
        if cmd[:4] == F1_PREFIX:
            self.handshakes += 1
        if _is_state_read(cmd):
            if self.expire_reads > 0:
                self.expire_reads -= 1
                return [_expired(cmd[3], cmd[4])]
            if _is_block27_read(cmd):
                return [_block27_reply(cmd)]
            return [self._state[STATE_READS[cmd]]]
        return self._handshake(cmd)


def _client(heater: ExpiringHeater):
    client = _client_with_matched_profile(heater)
    client._asset_id = b"02iQk000000EXAMPLE"
    return client


async def test_a_read_recovers_from_expiry_by_rechallenging_on_the_same_link(
    monkeypatch,
):
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    heater = ExpiringHeater(expire_reads=1)
    client = _client(heater)
    link = client._client

    state = await client.async_get_state()

    assert FieldName.SETPOINT in state
    assert heater.handshakes == 1
    assert client._client is link and link.is_connected


async def test_a_second_expiry_right_after_recovery_raises(monkeypatch):
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    heater = ExpiringHeater(expire_reads=2)
    client = _client(heater)

    with pytest.raises(SessionExpiredError):
        await client.async_get_state()
    assert heater.handshakes == 1


async def test_a_failed_rechallenge_falls_back_to_a_full_reconnect(monkeypatch):
    fresh = FakeBleakClient(ExpiringHeater(expire_reads=0))
    patch_establish(monkeypatch, fresh)

    def stale_responder(cmd: bytes) -> list[bytes]:
        if _is_state_read(cmd):
            return [_expired(cmd[3], cmd[4])]
        return []  # the re-challenge gets no answer

    client = _client_with_matched_profile(stale_responder)
    client._device = object()  # a BLEDevice stand-in, so no address scan
    client._asset_id = b"02iQk000000EXAMPLE"
    client._timeout = 0.05
    stale = client._client

    state = await client.async_get_state()

    assert FieldName.SETPOINT in state
    assert client._client is fresh
    assert stale.is_connected is False


async def test_a_write_after_expiry_recovers_in_its_state_read_and_is_sent_once(
    monkeypatch,
):
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    heater = ExpiringHeater(expire_reads=1)
    write = p.set_setpoint_request(124.0)
    word = int.from_bytes(write[5:7], "big")

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == write:
            ack = bytearray([0xDB, 0x02, 0x00, 11, 0, 0x80])
            ack[2] = len(ack) + 1
            return [crc_mod.frame(bytes(ack))]
        if cmd == p.read_request(11, 0, 1):
            body = bytearray([0xDB, 0x02, 0x00, 11, 0, word >> 8, word & 0xFF, 0x80])
            body[2] = len(body) + 1
            return [crc_mod.frame(bytes(body))]
        return heater(cmd)

    client = _client(heater)
    client._client._responder = responder

    await client.async_set_setpoint(124.0)

    assert heater.handshakes == 1
    assert client._client.written.count(write) == 1


async def test_an_expired_write_ack_is_settled_by_readback_and_not_resent(
    monkeypatch,
):
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)
    heater = ExpiringHeater(expire_reads=0)
    write = p.set_setpoint_request(120.0)
    old_value = _read_response(11, 0, bytes([0x33, 0x1C]))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == write:
            return [_expired(11, 0)]
        if cmd == p.read_request(11, 0, 1):
            return [old_value]
        return heater(cmd)

    client = _client(heater)
    client._client._responder = responder

    with pytest.raises(WriteUnconfirmedError, match="0x10"):
        await client.async_set_setpoint(120.0)
    assert heater.handshakes == 1  # the session was recovered for the readback
    assert client._client.written.count(write) == 1
