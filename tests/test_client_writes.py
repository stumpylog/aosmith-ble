import asyncio

import pytest

import aosmith_ble.crc as crc_mod
from aosmith_ble.client import AOSmithBLEClient
from aosmith_ble.const import Mode
from aosmith_ble.exceptions import ProtocolError, ValidationError
from aosmith_ble import protocol as p
from aosmith_ble.profiles import FieldSpec, Profile, Trust
from aosmith_ble.profiles.bundled import BUNDLED_PROFILES

from fake_transport import FakeBleakClient


def _profile_with_write_trust(field_name: str, trust: Trust) -> Profile:
    """A copy of the bundled profile with one field's write trust changed.

    Built as a fresh `Profile` rather than mutated in place, so the shared
    `BUNDLED_PROFILES` entry is never touched.
    """
    base = BUNDLED_PROFILES["hpts50-6.3"]
    fields = tuple(
        (
            name,
            FieldSpec(
                block=spec.block,
                param=spec.param,
                words=spec.words,
                codec=spec.codec,
                read=spec.read,
                write=trust if name == field_name else spec.write,
                scope=spec.scope,
            ),
        )
        for name, spec in base.fields
    )
    return Profile(
        id=base.id,
        match=base.match,
        min_setpoint_f=base.min_setpoint_f,
        max_setpoint_f=base.max_setpoint_f,
        allow_extended_max=base.allow_extended_max,
        writable_modes=base.writable_modes,
        fields=fields,
    )


def _healthy_state_responses() -> dict:
    """Every read async_get_state needs, wired to always report healthy/no fault.

    A real Block 11 full-page response is 47 bytes: a 5-byte header (header
    byte, cmd byte, length byte, then the block/start echo at indices 3-4),
    20 words (40 bytes) of data starting at index 5, a status byte, and a
    trailing CRC. `parse_read` strips indices 0-4 and the trailing status/CRC
    via `rsp[5:-2]`, so the block/start echo bytes must be present even
    though they're never part of the returned payload -- omitting them
    shifts every param index by one word and makes the last param
    (`electric_days_remaining`, index 19) unreachable.
    """
    body = (
        bytearray([0xDB, 0x02, 0x00, 0x0B, 0x00])
        + bytearray(2 * 20)
        + bytearray([0x80])
    )
    body[5] = 0x33  # setpoint high byte (payload word 0) -> arbitrary but present
    body[6] = 0x1C
    body[2] = len(body) + 1
    block11_bytes = crc_mod.frame(bytes(body))

    fault = bytearray([0xDB, 0x02, 0x00, 0x02, 0x07, 0x00, 0x00, 0x80])
    fault[2] = len(fault) + 1
    fault_bytes = crc_mod.frame(bytes(fault))
    return {"block11": block11_bytes, "fault": fault_bytes}


def _read_response(block: int, start: int, payload: bytes) -> bytes:
    body = (
        bytearray([0xDB, 0x02, 0x00, block, start])
        + bytearray(payload)
        + bytearray([0x80])
    )
    body[2] = len(body) + 1
    return crc_mod.frame(bytes(body))


def _client_with_matched_profile(responder) -> AOSmithBLEClient:
    fake = FakeBleakClient(responder)
    client = AOSmithBLEClient(device="AA:BB:CC:DD:EE:FF", pairing_code=b"123456")
    client._client = fake
    # FakeBleakClient starts disconnected with no notify callback registered until
    # .connect()/.start_notify() run (normally done by AOSmithBLEClient.connect());
    # these tests drive internal methods directly, so wire both by hand.
    fake.is_connected = True
    fake._notify_callback = client._on_notify
    client._session_ok = True
    client._profile = BUNDLED_PROFILES["hpts50-6.3"]
    return client


async def test_async_set_setpoint_refuses_above_absolute_ceiling():
    """The 140F ceiling holds even when the profile's own maximum does not.

    Every legitimately constructible profile is already validated to a
    maximum of 140F or below, so with a sound profile the profile-range
    check always fires first and the ceiling check is unreachable. That is
    exactly why it is worth testing: the only way to reach it is to hand the
    client a profile carrying a limit the profile validator would have
    rejected, which is the failure this backstop exists for. The limit is
    forced past the frozen dataclass here to build that otherwise
    impossible object.
    """
    client = _client_with_matched_profile(lambda cmd: [])
    broken = BUNDLED_PROFILES["hpts50-6.3"]
    object.__setattr__(broken, "max_setpoint_f", 145.0)
    try:
        client._profile = broken
        with pytest.raises(ValidationError, match="140"):
            await client.async_set_setpoint(145.0)
    finally:
        object.__setattr__(broken, "max_setpoint_f", 130)
    assert client._client.written == []


async def test_async_set_setpoint_refuses_above_profile_max():
    # 135 is below the 140 absolute ceiling but above this profile's own 130 max.
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="outside this device's supported range"):
        await client.async_set_setpoint(135.0)
    assert client._client.written == []


async def test_async_set_setpoint_refuses_below_profile_min():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="outside this device's supported range"):
        await client.async_set_setpoint(60.0)
    assert client._client.written == []


async def test_async_set_setpoint_refuses_nan():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError):
        await client.async_set_setpoint(float("nan"))
    assert client._client.written == []


async def test_async_set_mode_refuses_guest():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="not writable"):
        await client.async_set_mode(Mode.GUEST, duration_days=1)
    assert client._client.written == []


async def test_async_set_mode_refuses_unknown_mode_value():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="not writable"):
        await client.async_set_mode(99, duration_days=1)  # type: ignore[arg-type]
    assert client._client.written == []


async def test_async_set_mode_refuses_electric_with_zero_duration():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="non-zero duration"):
        await client.async_set_mode(Mode.ELECTRIC, duration_days=0)
    assert client._client.written == []


async def test_async_set_mode_refuses_vacation_with_zero_duration():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="non-zero duration"):
        await client.async_set_mode(Mode.VACATION, duration_days=0)
    assert client._client.written == []


async def test_async_set_mode_refuses_hybrid_with_nonzero_duration():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="permanent"):
        await client.async_set_mode(Mode.HYBRID, duration_days=3)
    assert client._client.written == []


async def test_async_set_mode_refuses_heat_pump_with_nonzero_duration():
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="permanent"):
        await client.async_set_mode(Mode.HEAT_PUMP, duration_days=1)
    assert client._client.written == []


@pytest.mark.parametrize("duration", [-1, 256, 1000])
async def test_async_set_mode_refuses_out_of_range_duration(duration):
    """An out-of-range duration must raise ValidationError, not a raw
    ValueError out of bytes(), and must not reach the link."""
    client = _client_with_matched_profile(lambda cmd: [])
    with pytest.raises(ValidationError, match="duration_days"):
        await client.async_set_mode(Mode.ELECTRIC, duration_days=duration)
    assert client._client.written == []


async def test_async_set_setpoint_refuses_while_fault_active():
    responses = _healthy_state_responses()
    fault_active = bytearray(
        [0xDB, 0x02, 0x00, 0x02, 0x07, 0x00, 0x1F, 0x80]
    )  # code 31, Water Leak
    fault_active[2] = len(fault_active) + 1
    fault_active_bytes = crc_mod.frame(bytes(fault_active))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [fault_active_bytes]
        return []

    client = _client_with_matched_profile(responder)
    with pytest.raises(ValidationError, match="fault"):
        await client.async_set_setpoint(124.0)
    assert p.set_setpoint_request(124.0) not in client._client.written


async def test_async_set_mode_refuses_while_fault_active():
    responses = _healthy_state_responses()
    fault_active = bytearray([0xDB, 0x02, 0x00, 0x02, 0x07, 0x00, 0x1F, 0x80])
    fault_active[2] = len(fault_active) + 1
    fault_active_bytes = crc_mod.frame(bytes(fault_active))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [fault_active_bytes]
        return []

    client = _client_with_matched_profile(responder)
    with pytest.raises(ValidationError, match="fault"):
        await client.async_set_mode(Mode.HYBRID)
    assert p.set_mode_request(int(Mode.HYBRID), 0) not in client._client.written


async def test_async_set_setpoint_happy_path_writes_and_verifies():
    responses = _healthy_state_responses()
    write_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x00, 0x80]))
    readback = bytearray([0xDB, 0x02, 0x00, 0x0B, 0x00, 0x33, 0x1C, 0x80])
    readback[2] = len(readback) + 1
    readback_bytes = crc_mod.frame(bytes(readback))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == p.set_setpoint_request(124.0):
            return [write_ack]
        if cmd == p.read_request(11, 0, 1):
            return [readback_bytes]
        return []

    client = _client_with_matched_profile(responder)
    await client.async_set_setpoint(124.0)  # must not raise


async def test_async_set_setpoint_raises_on_readback_mismatch():
    responses = _healthy_state_responses()
    write_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x00, 0x80]))
    wrong_readback = bytearray(
        [0xDB, 0x02, 0x00, 0x0B, 0x00, 0x00, 0x00, 0x80]
    )  # 0F, not 124F
    wrong_readback[2] = len(wrong_readback) + 1
    wrong_readback_bytes = crc_mod.frame(bytes(wrong_readback))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == p.set_setpoint_request(124.0):
            return [write_ack]
        if cmd == p.read_request(11, 0, 1):
            return [wrong_readback_bytes]
        return []

    client = _client_with_matched_profile(responder)
    with pytest.raises(ValidationError, match="did not take effect"):
        await client.async_set_setpoint(124.0)
    # The failed write is reported, never re-sent or corrected.
    assert client._client.written.count(p.set_setpoint_request(124.0)) == 1


async def test_async_set_setpoint_raises_when_the_device_rejects_the_write():
    responses = _healthy_state_responses()
    # Status byte 0x40 instead of 0x80: the device declined the write.
    refused_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x00, 0x40]))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == p.set_setpoint_request(124.0):
            return [refused_ack]
        return []

    client = _client_with_matched_profile(responder)
    with pytest.raises(ProtocolError, match="write rejected"):
        await client.async_set_setpoint(124.0)
    assert client._client.written.count(p.set_setpoint_request(124.0)) == 1


@pytest.mark.parametrize(
    "mode, duration",
    [(Mode.HYBRID, 0), (Mode.HEAT_PUMP, 0), (Mode.ELECTRIC, 2), (Mode.VACATION, 14)],
)
async def test_async_set_mode_happy_path_writes_and_verifies(mode, duration):
    responses = _healthy_state_responses()
    write_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x0F, 0x80]))
    readback = _read_response(0x0B, 0x0F, bytes([duration, int(mode)]))
    request = p.set_mode_request(int(mode), duration)

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == request:
            return [write_ack]
        if cmd == p.read_request(11, 15, 1):
            return [readback]
        return []

    client = _client_with_matched_profile(responder)
    await client.async_set_mode(mode, duration_days=duration)  # must not raise
    assert request in client._client.written


async def test_async_set_mode_raises_on_readback_mismatch():
    responses = _healthy_state_responses()
    write_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x0F, 0x80]))
    # The device reports ELECTRIC/2 still in force after a HYBRID write.
    wrong_readback = _read_response(0x0B, 0x0F, bytes([2, int(Mode.ELECTRIC)]))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == p.set_mode_request(int(Mode.HYBRID), 0):
            return [write_ack]
        if cmd == p.read_request(11, 15, 1):
            return [wrong_readback]
        return []

    client = _client_with_matched_profile(responder)
    with pytest.raises(ValidationError, match="did not take effect"):
        await client.async_set_mode(Mode.HYBRID)
    assert client._client.written.count(p.set_mode_request(int(Mode.HYBRID), 0)) == 1


async def test_a_timed_out_write_is_not_retried():
    """A write that gets no response raises and is sent exactly once: it may
    still have landed on the device, so re-sending could double-apply it."""
    responses = _healthy_state_responses()

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        return []  # silence for the write itself

    client = _client_with_matched_profile(responder)
    client._timeout = 0.05
    with pytest.raises(ProtocolError, match="no response"):
        await client.async_set_setpoint(124.0)
    assert client._client.written.count(p.set_setpoint_request(124.0)) == 1


async def test_a_write_does_not_deadlock_against_its_own_state_read():
    """The fault check reads state from inside the write's critical section.

    `self._lock` is a plain asyncio.Lock and is not reentrant, so the check
    must not go through the public, lock-taking read method. Bounded here so
    a regression fails as a test failure rather than hanging the suite.
    """
    responses = _healthy_state_responses()
    write_ack = crc_mod.frame(bytes([0xDB, 0x02, 0x07, 0x0B, 0x00, 0x80]))
    readback = _read_response(0x0B, 0x00, bytes([0x33, 0x1C]))

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        if cmd == p.set_setpoint_request(124.0):
            return [write_ack]
        if cmd == p.read_request(11, 0, 1):
            return [readback]
        return []

    client = _client_with_matched_profile(responder)
    await asyncio.wait_for(client.async_set_setpoint(124.0), timeout=5.0)
    # And the lock is released again afterwards, so the client stays usable.
    assert not client._lock.locked()
    await asyncio.wait_for(client.async_get_state(), timeout=5.0)


def test_the_bundled_profile_grades_both_write_paths_ok():
    """Guards the happy-path tests below: they only exercise a real write
    because this profile actually grades these two writes as observed."""
    fields = BUNDLED_PROFILES["hpts50-6.3"].field_map
    assert fields["setpoint"].write is Trust.OK
    assert fields["mode"].write is Trust.OK


@pytest.mark.parametrize("trust", [Trust.UNVERIFIED, Trust.PARTIAL, Trust.UNSUPPORTED])
async def test_async_set_setpoint_refuses_an_unverified_write_path(trust):
    client = _client_with_matched_profile(lambda cmd: [])
    client._profile = _profile_with_write_trust("setpoint", trust)
    with pytest.raises(ValidationError, match="not verified"):
        await client.async_set_setpoint(124.0)
    assert client._client.written == []


@pytest.mark.parametrize("trust", [Trust.UNVERIFIED, Trust.PARTIAL, Trust.UNSUPPORTED])
async def test_async_set_mode_refuses_an_unverified_write_path(trust):
    client = _client_with_matched_profile(lambda cmd: [])
    client._profile = _profile_with_write_trust("mode", trust)
    with pytest.raises(ValidationError, match="not verified"):
        await client.async_set_mode(Mode.HYBRID)
    assert client._client.written == []


async def test_an_unverified_write_path_is_refused_before_the_value_is_judged():
    """The trust refusal is categorical, so it outranks a value complaint.

    Reporting "135F is out of range" for a field that admits no value at all
    would imply some other value would have been accepted.
    """
    client = _client_with_matched_profile(lambda cmd: [])
    client._profile = _profile_with_write_trust("setpoint", Trust.UNSUPPORTED)
    with pytest.raises(ValidationError, match="not verified"):
        await client.async_set_setpoint(135.0)  # also above the profile's 130 max
    assert client._client.written == []


async def test_an_unverified_mode_write_path_is_refused_before_the_mode_is_judged():
    client = _client_with_matched_profile(lambda cmd: [])
    client._profile = _profile_with_write_trust("mode", Trust.UNSUPPORTED)
    with pytest.raises(ValidationError, match="not verified"):
        await client.async_set_mode(Mode.GUEST, duration_days=1)  # also not writable
    assert client._client.written == []


def test_a_demoted_inherited_write_is_refused_by_this_check():
    """resolve_inherits demotes an inherited write=Trust.OK to UNVERIFIED.

    That demotion is only meaningful if the write path enforces it, so pin
    the two together: a child profile that inherits `setpoint` without
    re-asserting it must come out ungraded, and therefore unwritable.
    """
    from aosmith_ble.profiles import Match, resolve_inherits

    parent = BUNDLED_PROFILES["hpts50-6.3"]
    child = Profile(
        id="child",
        match=Match(model=parent.match.model, firmware=(6, 4)),
        min_setpoint_f=parent.min_setpoint_f,
        max_setpoint_f=parent.max_setpoint_f,
        writable_modes=parent.writable_modes,
        fields=(),
        inherits=parent.id,
    )
    resolved = resolve_inherits({parent.id: parent, "child": child}, "child")
    assert resolved.field_map["setpoint"].write is Trust.UNVERIFIED
    assert resolved.field_map["mode"].write is Trust.UNVERIFIED


async def test_writes_refuse_cleanly_when_fault_is_not_readable_at_ok_trust():
    """A profile grading fault below OK leaves it out of the default-trust
    state read; the write must refuse with a clear error, not a KeyError."""
    from aosmith_ble.profiles import FieldName, FieldSpec, Trust

    base = BUNDLED_PROFILES["hpts50-6.3"]
    fields = tuple(
        (
            name,
            FieldSpec(
                block=spec.block,
                param=spec.param,
                words=spec.words,
                codec=spec.codec,
                read=Trust.PARTIAL,
                write=spec.write,
                scope=spec.scope,
            ),
        )
        if name == FieldName.FAULT
        else (name, spec)
        for name, spec in base.fields
    )
    profile = Profile(
        id=base.id,
        match=base.match,
        min_setpoint_f=base.min_setpoint_f,
        max_setpoint_f=base.max_setpoint_f,
        allow_extended_max=base.allow_extended_max,
        writable_modes=base.writable_modes,
        fields=fields,
    )
    responses = _healthy_state_responses()

    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(11, 0, 20):
            return [responses["block11"]]
        if cmd == p.read_request(2, 7, 1):
            return [responses["fault"]]
        return []

    client = _client_with_matched_profile(responder)
    client._profile = profile

    with pytest.raises(ValidationError, match="fault state not readable at OK trust"):
        await client.async_set_setpoint(120.0)
    write_prefix = p.write_request(11, 0, b"\x00\x00")[:2]
    assert not any(cmd[:2] == write_prefix for cmd in client._client.written)
