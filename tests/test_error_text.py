"""Library exception text and the connection name must carry no identifier or
credential-derived bytes: a host may log or display them verbatim."""

from __future__ import annotations

import bleak_retry_connector
import pytest
from fake_transport import FakeBleakClient
from test_client_hooks import patch_establish
from test_client_session import (
    ASSET_ID,
    _full_happy_path_responder,
    _make_client,
    _response,
)

from aosmith_ble import (
    AOSmithBLEClient,
    ConnectionSlotsExhaustedError,
    NotConnectedError,
    ProtocolError,
    pairing_code_from_name,
)
from aosmith_ble import client as client_mod
from aosmith_ble import protocol as p
from aosmith_ble.crc import check
from aosmith_ble.crc import frame as crc_frame

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "iCOMM-AC000W037XXXXXX"


def test_describe_frame_has_length_and_header_but_no_payload():
    frame = bytes.fromhex("db 02 09 11 22 33 44 55 66")

    text = p.describe_frame(frame)

    assert "9 bytes" in text
    assert "db 02 09" in text
    assert "11" not in text.replace("db 02 09", "")
    assert "44" not in text


def test_corrupted_init_response_does_not_leak_the_asset_id():
    # An init response (slot populated) carrying the assetID, with a bad CRC.
    asset = ASSET_ID.encode()
    body = bytes([0xDB, 0xF2, 24, 0x01]) + asset + bytes(1)
    good = crc_frame(body)
    bad = good[:-1] + bytes([good[-1] ^ 0xFF])
    assert not check(bad)
    assert asset in bad

    with pytest.raises(ProtocolError) as excinfo:
        p.parse_init(bad)

    message = str(excinfo.value)
    assert "CRC mismatch" in message
    assert asset.decode() not in message
    assert asset.hex() not in message.replace(" ", "")


def test_short_block0_style_response_does_not_leak_payload():
    payload = b"SN00001234"
    wrong_block = _response(payload, block=0, start=36)

    with pytest.raises(ProtocolError) as excinfo:
        p.parse_read(wrong_block, request_block=1, request_start=36, request_words=5)

    flat = str(excinfo.value).replace(" ", "")
    assert "echoed" in flat
    assert payload.decode() not in flat
    assert payload.hex() not in flat


async def test_timed_out_challenge_response_does_not_leak_the_hmac():
    base = _full_happy_path_responder()

    def responder(cmd: bytes) -> list[bytes]:
        if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
            return []  # silence: the exchange times out
        return base(cmd)

    client, _fake = await _make_client(responder)
    client._timeout = 0.05

    with pytest.raises(ProtocolError) as excinfo:
        await client._establish_session()

    hmac_hex = p.challenge_response(bytes.fromhex("9312"), ASSET_ID.encode())[
        4:24
    ].hex()
    assert "no response" in str(excinfo.value)
    assert hmac_hex not in str(excinfo.value).replace(" ", "")


async def test_connection_name_is_fixed_not_the_advertised_name(monkeypatch):
    class Device:
        name = NAME
        address = ADDRESS

    fake = FakeBleakClient(_full_happy_path_responder())
    calls = patch_establish(monkeypatch, fake)

    client = AOSmithBLEClient(device=Device(), pairing_code=b"123456")
    await client.connect()

    assert calls[0]["name"] == client_mod.CONNECTION_NAME == "iCOMM water heater"


async def test_device_not_found_message_has_no_address(monkeypatch):
    async def not_found(_address, timeout=20.0):
        return None

    monkeypatch.setattr(client_mod.BleakScanner, "find_device_by_address", not_found)
    client = AOSmithBLEClient(device=ADDRESS, pairing_code=b"123456")

    with pytest.raises(NotConnectedError) as excinfo:
        await client.connect()

    assert ADDRESS not in str(excinfo.value)
    assert ADDRESS.replace(":", "") not in str(excinfo.value)


async def test_slots_exhausted_message_is_fixed_and_cause_is_kept(monkeypatch):
    original = bleak_retry_connector.BleakOutOfConnectionSlotsError(
        f"no slots for {ADDRESS} {NAME}"
    )

    async def out_of_slots(_cls, _device, _name, **_kwargs):
        raise original

    monkeypatch.setattr(bleak_retry_connector, "establish_connection", out_of_slots)
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")

    with pytest.raises(ConnectionSlotsExhaustedError) as excinfo:
        await client.connect()

    assert ADDRESS not in str(excinfo.value)
    assert NAME not in str(excinfo.value)
    assert excinfo.value.__cause__ is original


def test_pairing_code_error_does_not_echo_the_name():
    with pytest.raises(ValueError) as excinfo:
        pairing_code_from_name("iCOMM-AB12")

    message = str(excinfo.value)
    assert "iCOMM" not in message
    assert "AB12" not in message
    assert "12" not in message
