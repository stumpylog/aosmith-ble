import json
from pathlib import Path

import pytest

from aosmith_ble import protocol as p
from aosmith_ble.client import AOSmithBLEClient, pairing_code_from_name
from aosmith_ble.const import CHAR_RX_UUID, STATUS_REFUSED
from aosmith_ble.crc import frame as crc_frame
from aosmith_ble.exceptions import (
    ConnectionSlotsExhaustedError,
    NotConnectedError,
    NotPairedError,
    SessionError,
    UnknownDeviceError,
    ValidationError,
)
from aosmith_ble.profiles.bundled import HPTS50_MODEL_BYTES
from fake_transport import FakeBleakClient

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


ASSET_ID = "02iQk000000EXAMPLE"


def _response(payload_after_echo: bytes, block: int, start: int) -> bytes:
    """Build a CRC-valid read response around a parameter payload.

    Wire shape is ``DB 02 <len> <block> <start> <payload...> 80 <crc>``, and
    the length byte counts the whole frame including the trailing CRC.
    """
    body = bytearray([0xDB, 0x02, 0x00, block, start]) + payload_after_echo + b"\x80"
    body[2] = len(body) + 1
    return crc_frame(bytes(body))


def _block0_page_one_hpts50_fw63() -> bytes:
    """A synthetic, CRC-valid Block 0 page-one response: firmware word 0x0603
    (v6.3), then params 1-15 zero, then HPTS50_MODEL_BYTES -- the SAME raw
    wire bytes bundled.py's Match.model uses, imported directly rather than
    reconstructed, so this test can never silently drift out of sync with
    what the matcher actually compares against -- across params 16-19. That
    is 20 words in total, exactly one full page."""
    assert len(HPTS50_MODEL_BYTES) == 8  # 4 words, matching the model FieldSpec
    payload = bytearray()
    payload += bytes([0x06, 0x03])  # param 0: firmware (hi=6, lo=3)
    payload += bytes(2 * 15)  # params 1-15
    payload += HPTS50_MODEL_BYTES  # params 16-19, raw wire bytes
    assert len(payload) == 40
    return _response(bytes(payload), block=0, start=0)


def _units_response(value: int) -> bytes:
    return _response(bytes([value >> 8, value & 0xFF]), block=26, start=2)


# The serial field's raw wire bytes at params 36-40: 5 words (10 bytes),
# word-swapped like the model field. A clean synthetic string, not a real
# hardware value -- built by swapping each adjacent byte pair of its ASCII
# encoding, the exact inverse of protocol.deswap_ascii.
SERIAL_HPTS50 = "SN00001234"
SERIAL_WORDS_HPTS50 = bytes(SERIAL_HPTS50.encode()[i ^ 1] for i in range(10))
assert SERIAL_WORDS_HPTS50 == bytes.fromhex("4e533030303032313433")


def _block0_page_two_serial() -> bytes:
    """Block 0, page two (start=36, 5 words) -- the serial field."""
    return _response(SERIAL_WORDS_HPTS50, block=0, start=36)


def _full_happy_path_responder():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.init_request():
            return [_fixture("init_response_slot_populated")]
        if cmd == p.challenge_request():
            return [_fixture("challenge_response_9312")]
        if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
            return [_fixture("f1_response_accepted")]
        if cmd == p.read_request(0, 0, 20):  # Block.IDENTITY
            return [_block0_page_one_hpts50_fw63()]
        if cmd == p.read_request(0, 36, 5):  # serial, identity-scoped
            return [_block0_page_two_serial()]
        if cmd == p.read_request(26, 2, 1):  # UNITS
            return [_units_response(0)]
        return []

    return responder


async def _make_client(responder, mtu_size: int = 100):
    """A client wired to a fake transport that is already linked up, i.e. the
    state `connect()` would have reached just before the session handshake."""
    fake = FakeBleakClient(responder, mtu_size=mtu_size)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    await fake.connect()
    client._client = fake
    await fake.start_notify(CHAR_RX_UUID, client._on_notify)
    return client, fake


async def test_connect_matches_profile_and_validates_session():
    client, _fake = await _make_client(_full_happy_path_responder())
    await client._establish_session()
    await client._match_and_validate_profile()
    assert client.profile is not None
    assert client.profile.id == "hpts50-6.3"


async def test_connect_populates_device_info():
    client, _fake = await _make_client(_full_happy_path_responder())
    await client._establish_session()
    await client._match_and_validate_profile()
    assert client.device_info.model == "HPTS-50"
    assert client.device_info.asset_id == ASSET_ID
    assert client.device_info.serial == SERIAL_HPTS50


def _responder_with_serial_read(serial_responses: list[bytes]):
    """The happy-path responder, but with the serial read answered by
    `serial_responses` instead (empty list = silence = a ProtocolError
    timeout)."""
    happy = _full_happy_path_responder()

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(0, 36, 5):
            return serial_responses
        return happy(cmd)

    return responder


def _refused_read(block: int, start: int) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start, STATUS_REFUSED])
    body[2] = len(body) + 1
    return crc_frame(bytes(body))


@pytest.mark.parametrize("failure", ["refused", "timeout"])
async def test_connect_survives_a_failed_serial_read(monkeypatch, failure):
    """The serial is a PARTIAL-graded, nice-to-have identity field: a
    refused or timed-out read of it must leave `serial=None`, never fail a
    `connect()` that every load-bearing check already passed."""
    import bleak_retry_connector

    from aosmith_ble import client as client_mod

    serial_responses = [_refused_read(0, 36)] if failure == "refused" else []
    fake = FakeBleakClient(_responder_with_serial_read(serial_responses))

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456", timeout=0.05)
    await client.connect()

    assert client.is_connected is True
    assert client.profile is not None
    assert client.device_info.model == "HPTS-50"
    assert client.device_info.serial is None


async def test_async_get_state_does_not_re_read_the_serial():
    """DeviceInfo.serial is fetched once, at connect time -- never repeated
    by a later async_get_state() poll."""
    client, fake = await _make_client(_full_happy_path_responder())
    await client._establish_session()
    await client._match_and_validate_profile()
    serial_reads_before = fake.written.count(p.read_request(0, 36, 5))
    assert serial_reads_before == 1

    # A minimal state read -- block 11 and block 2 param 7 both answer empty,
    # which is enough to exercise async_get_state() without a full fixture.
    fake._responder = lambda cmd: (
        [_response(bytes(40), block=11, start=0)]
        if cmd == p.read_request(11, 0, 20)
        else [_response(bytes(2), block=2, start=7)]
        if cmd == p.read_request(2, 7, 1)
        else []
    )
    await client.async_get_state()
    assert fake.written.count(p.read_request(0, 36, 5)) == serial_reads_before


def test_disconnect_resets_device_info():
    from aosmith_ble.client import AOSmithBLEClient
    from aosmith_ble.models import DeviceInfo

    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    object.__setattr__(client, "_info", DeviceInfo(model="X", serial="Y", asset_id="Z"))
    import asyncio

    asyncio.run(client.disconnect())
    assert client.device_info == DeviceInfo()


async def test_connect_raises_unknown_device_on_no_match():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(0, 0, 20):
            # 16 zero-words (params 0-15) then a differing 4-word (8-byte)
            # model field at params 16-19 -- 20 words total, matching a real
            # full-page response. (16 zero-words, not 15 -- params 0-15 is
            # 16 params, and the model field starts at param 16.)
            payload = bytes(2 * 16) + b"NOTHPTS!"
            return [_response(payload, block=0, start=0)]
        return []

    client, _fake = await _make_client(responder)
    with pytest.raises(UnknownDeviceError):
        await client._match_and_validate_profile()
    assert client.profile is None


async def test_connect_raises_validation_error_on_nonzero_units():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(0, 0, 20):
            return [_block0_page_one_hpts50_fw63()]
        if cmd == p.read_request(26, 2, 1):
            return [_units_response(1)]
        return []

    client, _fake = await _make_client(responder)
    with pytest.raises(ValidationError, match="UNITS"):
        await client._match_and_validate_profile()
    assert client.profile is None


async def test_connect_raises_validation_error_on_insufficient_mtu():
    client, _fake = await _make_client(_full_happy_path_responder(), mtu_size=23)
    with pytest.raises(ValidationError, match="MTU"):
        await client._match_and_validate_profile()
    assert client.profile is None


class _BluezLikeBackend:
    """Mimics bleak's BlueZ backend: a placeholder MTU until acquired."""

    def __init__(self, acquired: int | None, fail: bool = False) -> None:
        self._acquired = acquired
        self._fail = fail
        self._mtu_size: int | None = None

    async def _acquire_mtu(self) -> None:
        if self._fail:
            raise RuntimeError("AcquireWrite not supported")
        self._mtu_size = self._acquired


async def test_mtu_is_acquired_from_the_backend_when_bleak_reports_a_placeholder():
    # BlueZ reports 23 through mtu_size until the backend acquires the real value.
    client, fake = await _make_client(_full_happy_path_responder(), mtu_size=23)
    fake._backend = _BluezLikeBackend(acquired=151)
    await client._establish_session()
    await client._match_and_validate_profile()  # must not refuse
    assert client.profile is not None


async def test_acquired_mtu_that_is_really_too_small_is_still_refused():
    client, fake = await _make_client(_full_happy_path_responder(), mtu_size=100)
    fake._backend = _BluezLikeBackend(acquired=23)
    with pytest.raises(ValidationError, match="MTU"):
        await client._match_and_validate_profile()


async def test_unknown_mtu_is_not_treated_as_too_small():
    client, fake = await _make_client(_full_happy_path_responder(), mtu_size=23)
    fake._backend = _BluezLikeBackend(acquired=None, fail=True)
    assert await client._negotiated_mtu() is None
    await client._establish_session()
    await client._match_and_validate_profile()
    assert client.profile is not None


async def test_connect_raises_not_paired_when_slot_empty_and_no_cached_id():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.init_request():
            return [_fixture("init_response_slot_empty")]
        return []

    client, _fake = await _make_client(responder)
    with pytest.raises(NotPairedError):
        await client._establish_session()


async def test_connect_raises_session_error_when_challenge_rejected():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.init_request():
            return [_fixture("init_response_slot_populated")]
        if cmd == p.challenge_request():
            return [_fixture("challenge_response_9312")]
        if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
            return [_fixture("f1_response_rejected")]
        return []

    client, _fake = await _make_client(responder)
    with pytest.raises(SessionError):
        await client._establish_session()


async def test_session_uses_the_asset_id_the_device_reported():
    client, fake = await _make_client(_full_happy_path_responder())
    await client._establish_session()
    assert client.asset_id == ASSET_ID
    assert fake.written[0] == b"123456"


async def test_failed_connect_closes_the_link_instead_of_orphaning_it(monkeypatch):
    """A refusal must drop the BLE link, not just the session state.

    A device that fails to match refuses identically on every attempt, so a
    caller retrying `connect()` in a loop would otherwise strand one live
    connection per attempt, with nothing left holding a reference that could
    close it -- and a Bluetooth proxy has only a few connection slots.
    """
    import bleak_retry_connector

    from aosmith_ble import client as client_mod

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.init_request():
            return [_fixture("init_response_slot_populated")]
        if cmd == p.challenge_request():
            return [_fixture("challenge_response_9312")]
        if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
            return [_fixture("f1_response_accepted")]
        if cmd == p.read_request(0, 0, 20):
            return [_response(bytes(2 * 16) + b"NOTHPTS!", block=0, start=0)]
        return []

    fake = FakeBleakClient(responder)

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    # A non-string device skips the scanner lookup in connect().
    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    with pytest.raises(UnknownDeviceError):
        await client.connect()

    assert client._client is None
    assert client.is_connected is False
    assert fake.is_connected is False
    assert client.profile is None
    assert client._session_ok is False


async def test_connect_end_to_end_establishes_session_and_matches_profile(monkeypatch):
    """Drive the real `connect()`, not its internals, all the way through."""
    import bleak_retry_connector

    from aosmith_ble import client as client_mod

    fake = FakeBleakClient(_full_happy_path_responder())

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    await client.connect()

    assert client.is_connected is True
    assert client._session_ok is True
    assert client.profile is not None
    assert client.profile.id == "hpts50-6.3"
    assert client.asset_id == ASSET_ID
    assert client.device_info.model == "HPTS-50"


async def test_connect_wraps_out_of_connection_slots(monkeypatch):
    """The bleak_retry_connector exception must not leak to the caller."""
    import bleak_retry_connector

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        raise bleak_retry_connector.BleakOutOfConnectionSlotsError("no slots left")

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    with pytest.raises(ConnectionSlotsExhaustedError):
        await client.connect()
    assert client._client is None


async def test_connect_leaves_no_client_when_device_resolution_fails(monkeypatch):
    """`_open_link()` now runs inside `connect()`'s teardown `try` block, but
    a string device that the scanner can't find never gets as far as
    assigning `self._client` -- so there is nothing for the teardown's
    `client, self._client = self._client, None` to disconnect, same as
    before the refactor. Pin that traced invariant: no orphaned connection,
    no crash, a clean `NotConnectedError`.
    """
    from aosmith_ble import client as client_mod

    async def fake_find_device_by_address(_address, timeout=20.0):
        return None

    monkeypatch.setattr(
        client_mod.BleakScanner,
        "find_device_by_address",
        fake_find_device_by_address,
    )

    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    with pytest.raises(NotConnectedError):
        await client.connect()

    assert client._client is None
    assert client.is_connected is False


def test_pairing_code_from_name():
    assert pairing_code_from_name("iCOMM-AC000W037123456") == b"123456"
