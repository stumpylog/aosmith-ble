import aosmith_ble.crc as crc_mod
from aosmith_ble.client import AOSmithBLEClient
from aosmith_ble.const import Mode
from aosmith_ble.models import Feature
from aosmith_ble import protocol as p
from aosmith_ble.profiles import FieldName, Trust
from aosmith_ble.profiles.bundled import BUNDLED_PROFILES

from fake_transport import FakeBleakClient


def _block11_response(
    setpoint_word: int, duration: int, mode: int, v_days: int, g_days: int, e_days: int
) -> bytes:
    payload = bytes([0x0B, 0x00])
    payload += setpoint_word.to_bytes(2, "big")
    payload += bytes(2 * 14)  # params 1-14
    payload += ((duration << 8) | mode).to_bytes(2, "big")  # param 15
    payload += bytes(2)  # param 16
    payload += v_days.to_bytes(2, "big")  # param 17
    payload += g_days.to_bytes(2, "big")  # param 18
    payload += e_days.to_bytes(2, "big")  # param 19
    body = bytearray([0xDB, 0x02, 0x00]) + bytearray(payload) + bytearray([0x80])
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def _fault_healthy_response() -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, 0x02, 0x07, 0x00, 0x00, 0x80])
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def _client_with_matched_profile(responder) -> AOSmithBLEClient:
    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    fake.is_connected = True
    fake._notify_callback = client._on_notify
    client._session_ok = True
    client._profile = BUNDLED_PROFILES["hpts50-6.3"]
    return client


def _responder(block11: bytes, fault: bytes):
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [block11]
        if cmd == p.read_request(2, 7, 1):
            return [fault]
        return []

    return responder


async def test_async_get_state_decodes_through_the_profile():
    block11 = _block11_response(
        setpoint_word=0x331C,
        duration=2,
        mode=Mode.ELECTRIC,
        v_days=0,
        g_days=0,
        e_days=2,
    )
    client = _client_with_matched_profile(
        _responder(block11, _fault_healthy_response())
    )

    features = await client.async_get_state()

    setpoint = features[FieldName.SETPOINT]
    assert isinstance(setpoint, Feature)
    assert round(setpoint.value, 1) == 124.0
    assert setpoint.trust is Trust.OK
    assert setpoint.writable is True

    mode = features[FieldName.MODE]
    assert mode.value.mode == Mode.ELECTRIC
    assert mode.value.duration_days == 2

    assert features[FieldName.ELECTRIC_DAYS_REMAINING].value == 2
    assert features[FieldName.VACATION_DAYS_REMAINING].value == 0
    assert not features[FieldName.FAULT].value.active


async def test_async_get_state_default_min_trust_excludes_unverified_fields():
    block11 = _block11_response(
        setpoint_word=0x331C, duration=0, mode=Mode.HYBRID, v_days=0, g_days=5, e_days=0
    )
    client = _client_with_matched_profile(
        _responder(block11, _fault_healthy_response())
    )

    features = await client.async_get_state()

    # guest_days_remaining is graded Trust.UNVERIFIED in the bundled profile --
    # absent by default, not present with a placeholder value.
    assert FieldName.GUEST_DAYS_REMAINING not in features


async def test_async_get_state_opt_in_min_trust_includes_unverified_fields():
    block11 = _block11_response(
        setpoint_word=0x331C, duration=0, mode=Mode.HYBRID, v_days=0, g_days=5, e_days=0
    )
    client = _client_with_matched_profile(
        _responder(block11, _fault_healthy_response())
    )

    features = await client.async_get_state(min_trust=Trust.UNVERIFIED)

    assert features[FieldName.GUEST_DAYS_REMAINING].value == 5
    assert features[FieldName.GUEST_DAYS_REMAINING].trust is Trust.UNVERIFIED


async def test_async_get_state_identity_fields_never_appear():
    block11 = _block11_response(
        setpoint_word=0x331C, duration=0, mode=Mode.HYBRID, v_days=0, g_days=0, e_days=0
    )
    client = _client_with_matched_profile(
        _responder(block11, _fault_healthy_response())
    )

    features = await client.async_get_state(min_trust=Trust.UNVERIFIED)

    assert FieldName.MODEL not in features
    assert FieldName.SERIAL not in features


async def test_a_field_spanning_a_different_block_than_11_is_read_correctly():
    """Pins the fix for the latent "decode loop ignores spec.block" bug: a
    synthetic profile with a STATE field addressed outside Block 11 must be
    read from that field's own block, not from whatever Block 11 happened to
    return.
    """
    from aosmith_ble.profiles import FieldSpec, Match, Profile

    other_block_payload = (
        bytearray([0xDB, 0x02, 0x00, 0x05, 0x00])
        + bytearray([0x00, 0x2A])
        + bytearray([0x80])
    )
    other_block_payload[2] = len(other_block_payload) + 1
    other_block_response = crc_mod.frame(bytes(other_block_payload))

    profile = Profile(
        id="synthetic",
        match=Match(model=b"X", firmware=(1, 0)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(
            (
                FieldName.VACATION_DAYS_REMAINING,
                FieldSpec(block=5, param=0, words=1, codec="u16", read=Trust.OK),
            ),
        ),
    )

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(5, 0, 1):
            return [other_block_response]
        return []

    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    fake.is_connected = True
    fake._notify_callback = client._on_notify
    client._session_ok = True
    client._profile = profile

    features = await client.async_get_state()
    assert features[FieldName.VACATION_DAYS_REMAINING].value == 0x2A


def _client_with_profile(profile, responder) -> AOSmithBLEClient:
    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    fake.is_connected = True
    fake._notify_callback = client._on_notify
    client._session_ok = True
    client._profile = profile
    return client


def _block_response(block: int, start: int, words: tuple[int, ...]) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start])
    for word in words:
        body += word.to_bytes(2, "big")
    body.append(0x80)
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def _ok_plus_unsupported_profile():
    """One Trust.OK field at block 5 param 0 and one Trust.UNSUPPORTED field
    at block 5 param 3 -- they share a block, so a read covering both would
    be params 0-3, while a read of only the trusted one is param 0 alone."""
    from aosmith_ble.profiles import FieldSpec, Match, Profile

    return Profile(
        id="synthetic",
        match=Match(model=b"X", firmware=(1, 0)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(
            (
                FieldName.VACATION_DAYS_REMAINING,
                FieldSpec(block=5, param=0, words=1, codec="u16", read=Trust.OK),
            ),
            (
                FieldName.GUEST_DAYS_REMAINING,
                FieldSpec(
                    block=5, param=3, words=1, codec="u16", read=Trust.UNSUPPORTED
                ),
            ),
        ),
    )


def _refuses_unsupported_span_responder(cmd: bytes) -> list[bytes]:
    """Answers only a read of param 0 alone; the device refuses any read
    reaching the UNSUPPORTED param, as a real known-refused field would."""
    if cmd == p.read_request(5, 0, 1):
        return [_block_response(5, 0, (0x2A,))]
    body = bytearray([0xDB, 0x02, 0x00, 0x05, 0x00, 0x01])
    body[2] = len(body) + 1
    return [crc_mod.frame(bytes(body))]


async def test_an_unsupported_field_in_the_same_block_does_not_break_a_trusted_read():
    """Trust is filtered before reading, so an UNSUPPORTED field sharing a
    block with an OK one never widens (and so never breaks) the OK field's
    read."""
    client = _client_with_profile(
        _ok_plus_unsupported_profile(), _refuses_unsupported_span_responder
    )

    features = await client.async_get_state()

    assert features[FieldName.VACATION_DAYS_REMAINING].value == 0x2A
    assert FieldName.GUEST_DAYS_REMAINING not in features


async def test_unsupported_fields_never_appear_even_at_min_trust_unsupported():
    """trust_at_least(UNSUPPORTED, UNSUPPORTED) is True, so min_trust alone
    would admit UNSUPPORTED fields; they must be excluded regardless."""
    client = _client_with_profile(
        _ok_plus_unsupported_profile(), _refuses_unsupported_span_responder
    )

    features = await client.async_get_state(min_trust=Trust.UNSUPPORTED)

    assert FieldName.GUEST_DAYS_REMAINING not in features
    assert features[FieldName.VACATION_DAYS_REMAINING].value == 0x2A


async def test_a_block_span_wider_than_one_read_is_refused():
    """Two STATE fields in one block further apart than MAX_WORDS_PER_READ
    cannot be served by a single read; refuse rather than issue an
    oversized request the device cannot answer."""
    import pytest

    from aosmith_ble.const import MAX_WORDS_PER_READ
    from aosmith_ble.exceptions import ValidationError
    from aosmith_ble.profiles import FieldSpec, Match, Profile

    profile = Profile(
        id="synthetic",
        match=Match(model=b"X", firmware=(1, 0)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(
            (
                FieldName.VACATION_DAYS_REMAINING,
                FieldSpec(block=11, param=0, words=1, codec="u16", read=Trust.OK),
            ),
            (
                FieldName.ELECTRIC_DAYS_REMAINING,
                FieldSpec(block=11, param=25, words=1, codec="u16", read=Trust.PARTIAL),
            ),
        ),
    )
    assert 25 + 1 > MAX_WORDS_PER_READ
    client = _client_with_profile(profile, lambda cmd: [])

    with pytest.raises(ValidationError, match="single-read limit"):
        await client.async_get_state(min_trust=Trust.PARTIAL)
    assert client._client.written == []  # nothing oversized hit the wire
