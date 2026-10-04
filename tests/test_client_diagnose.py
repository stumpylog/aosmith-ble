import json
from pathlib import Path

import aosmith_ble.crc as crc_mod
from aosmith_ble import protocol as p
from aosmith_ble.client import AOSmithBLEClient
from aosmith_ble.const import CHAR_RX_UUID, STATUS_REFUSED
from aosmith_ble.profiles.bundled import HPTS50_MODEL_BYTES

from fake_transport import FakeBleakClient

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


def _response(payload_after_echo: bytes, block: int, start: int) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start]) + payload_after_echo + b"\x80"
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def _refused(block: int, start: int) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start, STATUS_REFUSED])
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


async def _make_client(responder, monkeypatch):
    import bleak_retry_connector

    from aosmith_ble import client as client_mod

    fake = FakeBleakClient(responder)

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    await fake.connect()
    client._client = fake
    await fake.start_notify(CHAR_RX_UUID, client._on_notify)
    return client, fake


def _handshake_responses(cmd: bytes) -> list[bytes] | None:
    if cmd == p.init_request():
        return [_fixture("init_response_slot_populated")]
    if cmd == p.challenge_request():
        return [_fixture("challenge_response_9312")]
    if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
        return [_fixture("f1_response_accepted")]
    return None


def test_build_raw_entries_keeps_ids_unique_across_same_label_captures():
    """`probe_presence()` calls `_raw_read` with no label at all, so two or
    more block probes share the same (empty) label -- and any future caller
    that reuses one label for multiple captures hits the same thing. The id
    must stay unique either way."""
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._capture_sink = [
        {"label": "", "request_hex": "aa", "response_hex": "bb"},
        {"label": "", "request_hex": "cc", "response_hex": "dd"},
        {"label": "diagnose_identity", "request_hex": "ee", "response_hex": "ff"},
    ]

    entries = client._build_raw_entries()

    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert len(entries) == 6  # one request + one response per capture


ASSET_ID = b"02iQk000000EXAMPLE"
NONCE = bytes.fromhex("9312")  # the nonce challenge_response_9312 carries


def _real_handshake_capture_sink() -> list[dict[str, str]]:
    """The three handshake exchanges exactly as `_exchange` would capture
    them, built from the real fixture frames, plus one ordinary read."""
    challenge_rsp = _fixture("challenge_response_9312")
    assert p.parse_challenge(challenge_rsp) == NONCE
    init_rsp = _fixture("init_response_slot_populated")
    assert p.parse_init(init_rsp) == (1, ASSET_ID)
    return [
        {
            "label": "init",
            "request_hex": p.init_request().hex(),
            "response_hex": init_rsp.hex(),
        },
        {
            "label": "challenge",
            "request_hex": p.challenge_request().hex(),
            "response_hex": challenge_rsp.hex(),
        },
        {
            "label": "challenge_response",
            "request_hex": p.challenge_response(NONCE, ASSET_ID).hex(),
            "response_hex": _fixture("f1_response_accepted").hex(),
        },
        {
            "label": "diagnose_identity",
            "request_hex": p.read_request(0, 0, 1).hex(),
            "response_hex": _response(bytes(2), block=0, start=0).hex(),
        },
    ]


def _assert_no_credential_material(entries) -> None:
    import hashlib
    import hmac

    asset_hex = ASSET_ID.hex()
    assert asset_hex == "02iQk000000EXAMPLE".encode().hex()
    digest_hex = hmac.new(NONCE, ASSET_ID, hashlib.sha1).hexdigest()
    challenge_frame_hex = _fixture("challenge_response_9312").hex()
    for entry in entries:
        assert asset_hex not in entry["hex"], entry
        assert digest_hex not in entry["hex"], entry
        assert challenge_frame_hex not in entry["hex"], entry
        assert NONCE.hex() not in entry["hex"], entry


def test_build_raw_entries_redacts_the_asset_id_nonce_and_hmac():
    """`init` carries the assetID; the `challenge` nonce plus the
    `challenge_response` HMAC are an offline brute-force oracle for it. None
    of the three may come out of `_build_raw_entries()` unredacted -- this
    output is meant to be pasted into public PRs."""
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    sink = _real_handshake_capture_sink()
    client._capture_sink = sink

    entries = client._build_raw_entries()

    _assert_no_credential_material(entries)
    # Sanity: the unredacted source material really did contain all of it,
    # so the assertions above are not vacuous.
    joined = "".join(c["request_hex"] + c["response_hex"] for c in sink)
    assert ASSET_ID.hex() in joined
    assert NONCE.hex() in joined
    # Redaction keeps the length (so fixture shape survives) and leaves the
    # ordinary read untouched.
    by_id = {entry["id"]: entry["hex"] for entry in entries}
    assert by_id["init_0_response"] == "00" * len(
        _fixture("init_response_slot_populated")
    )
    assert by_id["diagnose_identity_3_response"] == sink[3]["response_hex"]


async def test_async_diagnose_end_to_end_output_carries_no_credential_material(
    monkeypatch,
):
    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 1):
            return [_response(bytes(2), block=0, start=0)]
        return [_refused(0, 0)]

    client, _fake = await _make_client(responder, monkeypatch)
    diagnosis = await client.async_diagnose(max_block=0)

    labels = {entry["id"].rsplit("_", 2)[0] for entry in diagnosis.to_fixture_entries()}
    assert {"init", "challenge", "challenge_response"} <= labels
    _assert_no_credential_material(diagnosis.to_fixture_entries())


async def test_async_diagnose_disconnects_when_the_link_drops_midway(monkeypatch):
    """A dropped link (`NotConnectedError`) during the probe is not a single
    block's problem -- unlike a probe timeout (`ProtocolError`, tolerated --
    see the tests below), it must still abort the whole probe and the link
    must still be closed."""
    import pytest

    from aosmith_ble.exceptions import NotConnectedError

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 1):
            return [_response(bytes(2), block=0, start=0)]
        if cmd == p.read_request(1, 0, 1):
            fake.is_connected = False  # the link drops right before block 1's reply
            return []
        return [_refused(0, 0)]

    client, fake = await _make_client(responder, monkeypatch)
    client._timeout = 0.05

    with pytest.raises(NotConnectedError):
        await client.async_diagnose(max_block=2)

    assert client.is_connected is False
    assert fake.is_connected is False
    assert client._capture_sink is None


async def test_async_diagnose_tolerates_a_single_probe_timeout(monkeypatch):
    """A lone timeout on one probed block (e.g. an unresponsive block on an
    otherwise-live device) must not lose the whole report -- the block is
    recorded absent and the probe moves on."""

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 1):
            return [_response(bytes(2), block=0, start=0)]
        if cmd == p.read_request(1, 0, 1):
            return []  # block 1 times out
        if cmd == p.read_request(2, 0, 1):
            return [_response(bytes(2), block=2, start=0)]
        return [_refused(0, 0)]

    client, _fake = await _make_client(responder, monkeypatch)
    client._timeout = 0.05

    diagnosis = await client.async_diagnose(max_block=2)

    assert (0, 1) in diagnosis.block_presence
    assert (2, 1) in diagnosis.block_presence
    assert 1 not in {block for block, _ in diagnosis.block_presence}
    assert client.is_connected is False


async def test_async_diagnose_caps_a_fully_silent_device_at_the_consecutive_timeout_limit(
    monkeypatch,
):
    """A device that times out on every single probed block must still
    return promptly -- capped by `_MAX_CONSECUTIVE_TIMEOUTS` -- rather than
    probing all the way out to `max_block`."""
    from aosmith_ble.diagnostics import _MAX_CONSECUTIVE_TIMEOUTS

    probed_blocks: list[int] = []

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if len(cmd) >= 6 and cmd[4] == 0 and cmd[5] == 1:
            probed_blocks.append(cmd[3])
        return []  # every probed block, and the identity read, times out

    client, _fake = await _make_client(responder, monkeypatch)
    client._timeout = 0.02

    diagnosis = await client.async_diagnose(max_block=10)

    assert diagnosis.block_presence == ()
    assert diagnosis.model is None
    assert len(probed_blocks) == _MAX_CONSECUTIVE_TIMEOUTS
    assert client.is_connected is False


async def test_async_diagnose_keeps_a_partial_report_when_the_identity_read_times_out(
    monkeypatch,
):
    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 1):
            return [_response(bytes(2), block=0, start=0)]
        return []  # the 20-word identity read goes unanswered

    client, _fake = await _make_client(responder, monkeypatch)
    client._timeout = 0.05

    diagnosis = await client.async_diagnose(max_block=0)

    assert diagnosis.model is None
    assert diagnosis.firmware is None
    assert diagnosis.block_presence == ((0, 1),)
    assert client.is_connected is False


async def test_async_diagnose_closes_an_existing_connection_instead_of_orphaning_it(
    monkeypatch,
):
    import bleak_retry_connector

    from aosmith_ble import client as client_mod

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        return [_refused(0, 0)]

    old_link = FakeBleakClient(responder)
    new_link = FakeBleakClient(responder)

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await new_link.connect()
        return new_link

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    await old_link.connect()
    client._client = old_link
    await old_link.start_notify(CHAR_RX_UUID, client._on_notify)

    await client.async_diagnose(max_block=0)

    assert old_link.is_connected is False
    assert new_link.is_connected is False
    assert client.is_connected is False


async def test_async_diagnose_honors_the_release_window():
    import time

    import pytest

    from aosmith_ble.exceptions import NotConnectedError

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    client._released_until = time.monotonic() + 60

    with pytest.raises(NotConnectedError, match="released"):
        await client.async_diagnose(max_block=0)


async def test_async_diagnose_waits_for_the_client_lock(monkeypatch):
    import asyncio

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        return [_refused(0, 0)]

    client, fake = await _make_client(responder, monkeypatch)
    written_before = len(fake.written)

    async with client._lock:
        task = asyncio.create_task(client.async_diagnose(max_block=0))
        await asyncio.sleep(0.05)
        assert not task.done()
        assert len(fake.written) == written_before  # nothing hit the wire
    await task
    assert client.is_connected is False


async def test_async_diagnose_reports_block_presence_for_an_unmatched_device(
    monkeypatch,
):
    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        # The probe's own 1-word read of block 0 and the identity read's
        # full 20-word read of block 0 are different wire requests -- both
        # must be handled, or the probe's block-0 call falls through to the
        # refused default below and block 0 is wrongly reported absent.
        if cmd == p.read_request(0, 0, 1):
            return [_response(bytes(2), block=0, start=0)]
        if cmd == p.read_request(0, 0, 20):
            return [_response(bytes(2 * 16) + b"NOTHPTS!", block=0, start=0)]
        if cmd == p.read_request(1, 0, 1):
            return [_response(bytes(2), block=1, start=0)]
        return [_refused(0, 0)]  # every other probed block refuses

    client, _fake = await _make_client(responder, monkeypatch)
    report = client.profile  # sanity: nothing matched yet
    assert report is None

    diagnosis = await client.async_diagnose(max_block=2)

    assert (0, 1) in diagnosis.block_presence
    assert (1, 1) in diagnosis.block_presence
    assert diagnosis.decoded_values.get("matched_profile") is None
    assert client.is_connected is False  # always disconnects when done


async def test_async_diagnose_reports_the_matched_profile_when_the_device_matches(
    monkeypatch,
):
    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 20):
            payload = bytearray()
            payload += bytes([0x06, 0x03])
            payload += bytes(2 * 15)
            payload += HPTS50_MODEL_BYTES
            return [_response(bytes(payload), block=0, start=0)]
        return [_refused(0, 0)]

    client, _fake = await _make_client(responder, monkeypatch)
    diagnosis = await client.async_diagnose(max_block=0)

    assert diagnosis.decoded_values.get("matched_profile") == "hpts50-6.3"
    assert client.is_connected is False


async def test_async_diagnose_does_not_corrupt_state_for_a_later_real_connect(
    monkeypatch,
):
    """A device that matches during diagnose() must still be connectable
    normally afterward -- diagnose() must not leave _profile/_session_ok in
    a state connect() would trip over."""
    import bleak_retry_connector
    from aosmith_ble import client as client_mod

    def responder(cmd: bytes) -> list[bytes]:
        handshake = _handshake_responses(cmd)
        if handshake is not None:
            return handshake
        if cmd == p.read_request(0, 0, 20):
            payload = bytearray()
            payload += bytes([0x06, 0x03])
            payload += bytes(2 * 15)
            payload += HPTS50_MODEL_BYTES
            return [_response(bytes(payload), block=0, start=0)]
        if cmd == p.read_request(0, 36, 5):
            return [_response(bytes(10), block=0, start=36)]
        if cmd == p.read_request(26, 2, 1):
            return [_response(bytes([0, 0]), block=26, start=2)]
        return [_refused(0, 0)]

    fake = FakeBleakClient(responder)

    async def fake_establish_connection(_cls, _device, _name, **_kwargs):
        await fake.connect()
        return fake

    monkeypatch.setattr(
        bleak_retry_connector, "establish_connection", fake_establish_connection
    )
    monkeypatch.setattr(client_mod, "_SETTLE", 0.0)

    client = AOSmithBLEClient(device=object(), pairing_code=b"123456")
    await client.async_diagnose(max_block=0)
    assert client._session_ok is False
    assert client._profile is None

    await client.connect()
    assert client._session_ok is True
    assert client.profile is not None
    assert client.profile.id == "hpts50-6.3"
