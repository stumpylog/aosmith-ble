"""Async BLE client for A.O. Smith iCOMM heat pump water heaters.

This is the only module in the package that imports Bluetooth machinery, and
the only path in the whole package that can write to a device -- every write
goes through the profile-gated choke point (see the write methods on this
class).
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import TracebackType

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import codecs as c
from . import protocol as p
from .const import (
    CHAR_RX_UUID,
    CHAR_TX_UUID,
    MAX_WORDS_PER_READ,
    NAME_PREFIX,
    Block,
    Mode,
)
from .diagnostics import DiagnosticReport, probe_presence
from .exceptions import (
    ConnectionSlotsExhaustedError,
    NotConnectedError,
    NotPairedError,
    ProtocolError,
    ReadRefusedError,
    SessionError,
    UnknownDeviceError,
    ValidationError,
)
from .models import DeviceInfo, Feature, FeatureSet
from .profiles import FieldName, FieldScope, FieldSpec, Profile, Trust, trust_at_least
from .profiles.bundled import match_profile

_LOGGER = logging.getLogger(__name__)

_PAIRING_CODE_LEN = 6
DEFAULT_TIMEOUT = 8.0
_SETTLE = 0.4
_MIN_MTU = 50  # 47-byte Block 11 response + a 3-byte ATT header margin
_UNITS_BLOCK = 26
_UNITS_PARAM = 2

# Capture labels whose request or response bytes are credential-bearing and
# must never leave `_build_raw_entries()` unredacted. `init` carries the
# assetID in plaintext. `challenge` (the plaintext 2-byte nonce) and
# `challenge_response` (HMAC-SHA1 keyed with that nonce over the assetID)
# together form an offline oracle: the assetID's unknown portion is small
# enough to brute-force against them. Publishing any of the three is
# publishing control of the device to anyone in radio range.
_SENSITIVE_CAPTURE_LABELS = frozenset({"init", "challenge", "challenge_response"})


def pairing_code_from_name(name: str) -> bytes:
    """``iCOMM-AC000W037123456`` -> ``b"123456"``."""
    digits = "".join(ch for ch in name if ch.isdigit())
    if len(digits) < _PAIRING_CODE_LEN:
        raise ValueError(f"cannot derive pairing code from {name!r}")
    return digits[-_PAIRING_CODE_LEN:].encode()


async def async_discover(timeout: float = 20.0) -> list[BLEDevice]:
    devices = await BleakScanner.discover(timeout=timeout)
    return [d for d in devices if (d.name or "").startswith(NAME_PREFIX)]


class AOSmithBLEClient:
    """Talks the iCOMM BLE protocol over a single connection.

    The device only serves real data after a per-connection challenge AND a
    matched device profile, so both are re-established on every connect.
    """

    def __init__(
        self,
        device: BLEDevice | str,
        pairing_code: bytes | str,
        asset_id: bytes | str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._device = device
        self._pairing_code = (
            pairing_code.encode() if isinstance(pairing_code, str) else pairing_code
        )
        self._asset_id: bytes | None = (
            asset_id.encode() if isinstance(asset_id, str) else asset_id
        )
        self._timeout = timeout
        self._client: BleakClient | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._session_ok = False
        self._profile: Profile | None = None
        self._info = DeviceInfo()
        self._released_until: float = 0.0
        self._capture_sink: list[dict[str, str]] | None = None

    @property
    def asset_id(self) -> str | None:
        return self._asset_id.decode() if self._asset_id else None

    @property
    def profile(self) -> Profile | None:
        return self._profile

    @property
    def device_info(self) -> DeviceInfo:
        return self._info

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def __aenter__(self) -> AOSmithBLEClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    async def _open_link(self) -> None:
        """Establish the BLE link and wire up notifications -- no session,
        no profile match. Shared by `connect()` and `async_diagnose()`,
        which otherwise have incompatible failure/teardown semantics."""
        device = self._device
        if isinstance(device, str):
            found = await BleakScanner.find_device_by_address(device, timeout=20.0)
            if found is None:
                raise NotConnectedError(f"device {device} not found")
            device = found

        try:
            from bleak_retry_connector import (
                BleakOutOfConnectionSlotsError,
                establish_connection,
            )

            try:
                self._client = await establish_connection(
                    BleakClient, device, getattr(device, "name", None) or str(device)
                )
            except BleakOutOfConnectionSlotsError as err:
                raise ConnectionSlotsExhaustedError(str(err)) from err
        except ImportError:  # pragma: no cover - fallback for non-HA use
            self._client = BleakClient(device, timeout=30.0)
            await self._client.connect()

        await self._client.start_notify(CHAR_RX_UUID, self._on_notify)
        await asyncio.sleep(0.2)

    async def _negotiated_mtu(self) -> int | None:
        """The ATT MTU, or None when it cannot be determined.

        On BlueZ, bleak reports a placeholder of 23 from `mtu_size` until its
        backend's `_acquire_mtu()` has run, and nothing runs it for us, so a
        direct read always looks too small. Ask the backend to acquire the
        real value when it can. If that fails the MTU is unknown, not small:
        an undersized MTU would truncate a response and fail its CRC or
        length check rather than decode wrongly, so only a positively known
        small value is refused.
        """
        client = self._client
        if client is None:
            return None
        backend = getattr(client, "_backend", None)
        acquire = getattr(backend, "_acquire_mtu", None)
        if acquire is None:
            return client.mtu_size
        try:
            await acquire()
        except Exception:  # noqa: BLE001 - any failure means "unknown"
            return None
        return getattr(backend, "_mtu_size", None)

    async def connect(self) -> None:
        if self.is_connected and self._session_ok:
            return
        if time.monotonic() < self._released_until:
            raise NotConnectedError(
                f"connection released until {self._released_until - time.monotonic():.0f}s from now"
            )

        try:
            await self._open_link()
            await self._establish_session()
            await self._match_and_validate_profile()
        except BaseException:
            # Close the link too, not just the session state. A refused
            # device (an unmatched profile, a bad MTU) fails the same way on
            # every attempt, so a caller retrying in a loop would otherwise
            # leave one orphaned connection behind per attempt, with no
            # reference left to close it -- and a Bluetooth proxy has only a
            # handful of connection slots to lose.
            self._session_ok = False
            self._profile = None
            client, self._client = self._client, None
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # pragma: no cover - never mask the real error
                    _LOGGER.debug(
                        "failed to close the link after a failed connect",
                        exc_info=True,
                    )
            raise

    async def disconnect(self) -> None:
        self._session_ok = False
        self._profile = None
        self._info = DeviceInfo()
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None

    async def async_release(self, seconds: float) -> None:
        """Drop the connection and refuse to reconnect for `seconds`, so the
        manufacturer's app (the natural recovery path if this library ever
        leaves the device in an unwanted state) can connect instead."""
        await self.disconnect()
        self._released_until = time.monotonic() + seconds

    async def async_diagnose(self, max_block: int = 40) -> DiagnosticReport:
        """Connect, probe, and disconnect independently of `connect()`'s
        normal failure semantics -- the one path that can reach a connected,
        session-established client for a device `connect()` would refuse
        outright (an unmatched profile), so a contributor can still get a
        usable report out of it.

        Honors an `async_release()` window exactly like `connect()`, holds
        `self._lock` throughout so no poll or write can interleave on the
        shared notify queue, and tears down any existing connection first
        rather than overwriting (and orphaning) it.

        The release-window check is re-done after the lock is acquired, not
        only before: if this call is queued behind an in-flight write and
        `async_release()` runs while it waits, checking only before waiting
        would let it proceed into the release window once the lock frees up.
        """
        async with self._lock:
            if time.monotonic() < self._released_until:
                raise NotConnectedError(
                    f"connection released until {self._released_until - time.monotonic():.0f}s from now"
                )
            if self.is_connected:
                await self.disconnect()
            return await self._diagnose_unlocked(max_block)

    async def _diagnose_unlocked(self, max_block: int) -> DiagnosticReport:
        """The body of `async_diagnose`; the caller holds `self._lock`."""
        self._capture_sink = []
        try:
            await self._open_link()
            await self._establish_session()
            block_presence = await probe_presence(self, max_block=max_block)

            model: bytes | None = None
            firmware: tuple[int, int] | None = None
            matched_id: str | None = None
            try:
                head = await self._raw_read(
                    Block.IDENTITY, 0, MAX_WORDS_PER_READ, label="diagnose_identity"
                )
                model_words = tuple(p.param(head, i) for i in range(16, 20))
                model = b"".join(w.to_bytes(2, "big") for w in model_words)
                firmware_word = p.param(head, 0)
                firmware = (firmware_word >> 8, firmware_word & 0xFF)
                matched = match_profile(model, firmware)
                matched_id = matched.id if matched else None
            except (ReadRefusedError, SessionError, ProtocolError):
                # A refused, timed-out or malformed identity read still
                # yields a partial report (model/firmware left None) rather
                # than discarding everything captured so far.
                _LOGGER.debug("identity read failed during diagnose", exc_info=True)

            raw_entries = self._build_raw_entries()
            return DiagnosticReport(
                model=model,
                firmware=firmware,
                block_presence=block_presence,
                decoded_values={
                    "asset_id": self.asset_id,
                    "matched_profile": matched_id,
                },
                raw_entries=raw_entries,
            )
        finally:
            self._capture_sink = None
            await self.disconnect()

    def _build_raw_entries(self) -> tuple[dict[str, str], ...]:
        """Turn the capture sink's labeled request/response pairs into
        `tests/fixtures/frames.json`-shaped entries, one per direction.

        Every label in `_SENSITIVE_CAPTURE_LABELS` (the handshake's `init`,
        `challenge` and `challenge_response` exchanges) is zeroed out: `init`
        carries the assetID outright, and the nonce plus its HMAC together
        let anyone brute-force it offline. Every other label is a plain read
        with nothing credential-bearing in either direction -- including, in
        practice, an empty label: `probe_presence()`'s own
        `_raw_read` calls pass no label at all, so every block it probes
        would otherwise share one id. A running index is folded into every
        id (not just the empty-label ones) so ids stay unique regardless of
        what label, if any, a given capture carries.
        """
        captures = self._capture_sink or []
        entries: list[dict[str, str]] = []
        for index, capture in enumerate(captures):
            label = capture["label"]
            sensitive = label in _SENSITIVE_CAPTURE_LABELS
            for direction, hex_value in (
                ("request", capture["request_hex"]),
                ("response", capture["response_hex"]),
            ):
                entries.append(
                    {
                        "id": f"{label}_{index}_{direction}",
                        "hex": "00" * (len(hex_value) // 2) if sensitive else hex_value,
                        "source": "capture",
                        "note": (
                            f"redacted: {label} {direction} is assetID-derived"
                            if sensitive
                            else f"captured during async_diagnose(): {label} {direction}"
                        ),
                    }
                )
        return tuple(entries)

    def _on_notify(self, _char: object, data: bytearray) -> None:
        raw = bytes(data)
        if p.is_at_command(raw):
            _LOGGER.debug("dropping unsolicited AT command: %r", raw)
            return
        self._queue.put_nowait(raw)

    async def _exchange(
        self, cmd: bytes, timeout: float | None = None, *, label: str = ""
    ) -> bytes:
        if self._client is None or not self._client.is_connected:
            raise NotConnectedError("not connected")
        while not self._queue.empty():
            self._queue.get_nowait()
        await self._client.write_gatt_char(CHAR_TX_UUID, cmd, response=True)
        try:
            response = await asyncio.wait_for(
                self._queue.get(), timeout or self._timeout
            )
        except asyncio.TimeoutError as err:
            raise ProtocolError(f"no response to {cmd.hex(' ')}") from err
        if self._capture_sink is not None:
            self._capture_sink.append(
                {
                    "label": label,
                    "request_hex": cmd.hex(),
                    "response_hex": response.hex(),
                }
            )
        return response

    async def _establish_session(self) -> None:
        assert self._client is not None
        await self._client.write_gatt_char(
            CHAR_TX_UUID, self._pairing_code, response=True
        )
        await asyncio.sleep(_SETTLE)

        status, asset = p.parse_init(
            await self._exchange(p.init_request(), label="init")
        )
        if status:
            self._asset_id = asset
        elif self._asset_id is None:
            raise NotPairedError(
                "pairing slot is empty and no assetID was cached; press the "
                "Bluetooth button on the control panel once, then retry"
            )

        challenge = p.parse_challenge(
            await self._exchange(p.challenge_request(), label="challenge")
        )
        rsp = await self._exchange(
            p.challenge_response(challenge, self._asset_id), label="challenge_response"
        )
        if not p.challenge_accepted(rsp):
            raise SessionError(
                "challenge rejected; the cached assetID is probably wrong"
            )
        self._session_ok = True

    async def _raw_read(
        self, block: int, start: int, words: int, *, label: str = ""
    ) -> bytes:
        rsp = await self._exchange(p.read_request(block, start, words), label=label)
        return p.parse_read(
            rsp, request_block=block, request_start=start, request_words=words
        )

    async def _match_and_validate_profile(self) -> None:
        head = await self._raw_read(Block.IDENTITY, 0, MAX_WORDS_PER_READ)
        # Params 16-19 of Block 0 hold the model field. This read starts at
        # param 0, so the payload's word index equals the param number
        # directly -- word index 16, not 4.
        model_words = tuple(p.param(head, i) for i in range(16, 20))
        model_bytes = b"".join(w.to_bytes(2, "big") for w in model_words)
        firmware_word = p.param(head, 0)
        firmware = (firmware_word >> 8, firmware_word & 0xFF)

        profile = match_profile(model_bytes, firmware)
        if profile is None:
            raise UnknownDeviceError(
                f"no bundled profile for model={model_bytes!r} firmware={firmware}"
            )

        mtu = await self._negotiated_mtu()
        if mtu is not None and mtu < _MIN_MTU:
            raise ValidationError(
                f"negotiated MTU {mtu} is too small "
                f"(need at least {_MIN_MTU} for a full Block 11 response)"
            )

        units_payload = await self._raw_read(_UNITS_BLOCK, _UNITS_PARAM, 1)
        units = p.param(units_payload, 0)
        if units != 0:
            raise ValidationError(
                f"device UNITS={units} (expected 0=Fahrenheit); this "
                "library's codecs assume Fahrenheit-from-Celsius×256 "
                "unconditionally and would decode/encode incorrectly"
            )

        self._profile = profile

        identity_fields = [
            (name, spec)
            for name, spec in profile.fields
            if spec.scope is FieldScope.IDENTITY and name != FieldName.MODEL
        ]
        # Best-effort: these fields (the serial today) are nice-to-have and
        # may be graded below OK, so a refused, failed or malformed read
        # leaves them None rather than failing a connect that every
        # load-bearing check above has already passed.
        serial = None
        try:
            identity_values = await self._read_fields_grouped_by_block(identity_fields)
            if FieldName.SERIAL in identity_values:
                serial_spec = profile.field_map[FieldName.SERIAL]
                serial = c.CODEC_REGISTRY[serial_spec.codec].decode(
                    identity_values[FieldName.SERIAL]
                )
        except (ReadRefusedError, SessionError, ProtocolError):
            _LOGGER.debug(
                "identity field read failed; serial left unset", exc_info=True
            )

        self._info = DeviceInfo(
            model=p.deswap_ascii(model_bytes),
            serial=serial,
            asset_id=self.asset_id,
        )

    async def async_get_state(self, min_trust: Trust = Trust.OK) -> FeatureSet:
        """Read every `FieldScope.STATE` field the matched profile declares,
        decoded through its own codec, filtered to fields graded at least
        `min_trust`. A field graded below `min_trust` is simply absent from
        the result -- never present with a placeholder value."""
        async with self._lock:
            return await self._read_state(min_trust)

    async def _read_state(self, min_trust: Trust = Trust.OK) -> FeatureSet:
        """The body of `async_get_state`, without taking `self._lock`.

        Split out because the write methods must read current state (to
        refuse while a fault is active) from inside the same critical
        section that then performs the write -- and `asyncio.Lock` is not
        reentrant, so calling the public method from there would deadlock.
        """
        if not self.is_connected or not self._session_ok or self._profile is None:
            await self.connect()
        assert self._profile is not None
        profile = self._profile

        # Filter on trust BEFORE reading, never after: an untrusted field
        # sharing a block read with trusted ones must not be able to break
        # that read for them. UNSUPPORTED means known absent or refused, so
        # it is excluded unconditionally -- trust_at_least(UNSUPPORTED,
        # UNSUPPORTED) is True, so min_trust alone would let it through.
        state_fields = [
            (name, spec)
            for name, spec in profile.fields
            if spec.scope is FieldScope.STATE
            and spec.read is not Trust.UNSUPPORTED
            and trust_at_least(spec.read, min_trust)
        ]
        raw_by_field = await self._read_fields_grouped_by_block(state_fields)

        features: dict[FieldName, Feature] = {}
        for name, spec in state_fields:
            value = c.CODEC_REGISTRY[spec.codec].decode(raw_by_field[name])
            features[name] = Feature(
                id=name, value=value, trust=spec.read, writable=spec.write is Trust.OK
            )
        return features

    async def _read_fields_grouped_by_block(
        self, named_specs: list[tuple[FieldName, FieldSpec]]
    ) -> dict[FieldName, tuple[int, ...]]:
        """One raw read per distinct block, covering every field's own
        param/words span within it, then slice each field's words back out.

        This is what actually fixes the "decode loop ignores spec.block" bug:
        every field is read from the block *it* declares, not from whatever
        Block 11 page the caller happened to already have in hand. For the
        bundled profile this reduces to exactly the two reads it always
        made (Block 11 params 0-19, Block 2 param 7), since every field in
        it already lives at an offset within one of those two spans.
        """
        by_block: dict[int, list[tuple[FieldName, FieldSpec]]] = {}
        for name, spec in named_specs:
            by_block.setdefault(spec.block, []).append((name, spec))

        result: dict[FieldName, tuple[int, ...]] = {}
        for block, entries in by_block.items():
            start = min(spec.param for _name, spec in entries)
            end = max(spec.param + spec.words for _name, spec in entries)
            if end - start > MAX_WORDS_PER_READ:
                names = ", ".join(str(name) for name, _spec in entries)
                raise ValidationError(
                    f"fields {names} in block {block} span params {start}-{end - 1} "
                    f"({end - start} words), wider than the {MAX_WORDS_PER_READ}-word "
                    "single-read limit; multi-page reads are not supported, refusing"
                )
            payload = await self._raw_read(
                block, start, end - start, label=f"read_block{block}_start{start}"
            )
            for name, spec in entries:
                offset = spec.param - start
                result[name] = tuple(
                    p.param(payload, offset + i) for i in range(spec.words)
                )
        return result

    # -- Writes ------------------------------------------------------------
    #
    # The only two public write methods in this package are below, and both
    # funnel through _write_and_verify. Nothing else anywhere writes a
    # parameter to a device.

    _TIMED_MODES = (Mode.ELECTRIC, Mode.VACATION, Mode.GUEST)

    async def _refuse_if_fault_active(self) -> None:
        """Refuse to write while the device reports any fault.

        Costs a full state read before every write; that is deliberate --
        any non-zero fault code puts the device in read-only mode, matching
        what the manufacturer's own app does with its controls.
        """
        features = await self._read_state()
        fault_feature = features.get(FieldName.FAULT)
        if fault_feature is None:
            raise ValidationError(
                "fault state not readable at OK trust; refusing write"
            )
        fault = fault_feature.value
        if fault.active:
            raise ValidationError(
                f"write refused: fault {fault.code} ({fault.name}) is active"
            )

    @staticmethod
    def _writable_spec(profile: Profile, field_name: str) -> FieldSpec:
        """Look up a field and refuse it unless its write path is graded OK.

        A field's write trust is graded independently of its read trust, and
        `resolve_inherits` deliberately demotes an inherited `write=Trust.OK`
        to `UNVERIFIED` unless a child profile re-asserts it. That grading
        only means anything if something enforces it, and the write choke
        point is the only place that can: below this line the value is on
        the wire.

        This is checked before the value itself, because it is categorical.
        An ungraded write path admits no value at all, so reporting a range
        or mode problem first would imply some other value would have been
        accepted, which is the opposite of true.
        """
        spec = profile.field_map[field_name]
        if spec.write is not Trust.OK:
            raise ValidationError(
                f"{field_name} write is not verified on this device "
                f"(trust={spec.write.name}); refusing"
            )
        return spec

    async def _write_and_verify(
        self, request: bytes, block: int, param: int, expected_words: tuple[int, ...]
    ) -> None:
        """Write one parameter, confirm the ack, then read the value back.

        A mismatch on read-back raises; it is never silently re-sent or
        corrected. A write that times out raises out of ``_exchange`` and is
        never retried either: a timed-out write may still have landed on the
        device, so retrying could double-apply it.
        """
        rsp = await self._exchange(request)
        if not p.write_accepted(rsp, block, param):
            raise ProtocolError(f"write rejected: {rsp.hex(' ')}")
        readback = await self._raw_read(block, param, len(expected_words))
        actual = tuple(p.param(readback, i) for i in range(len(expected_words)))
        if actual != expected_words:
            raise ValidationError(
                f"write to block {block} param {param} did not take effect: "
                f"wrote {expected_words}, read back {actual}"
            )

    async def async_set_setpoint(self, degf: float) -> None:
        """Set the operating setpoint in Fahrenheit. Refused outside the
        matched profile's own limits, and unconditionally outside the
        absolute 140F ceiling regardless of profile."""
        async with self._lock:
            if not self.is_connected or not self._session_ok or self._profile is None:
                await self.connect()
            assert self._profile is not None
            profile = self._profile

            spec = self._writable_spec(profile, "setpoint")
            # encode_setpoint_f below implements exactly one encoding, so a
            # profile that declares a different codec for this field would
            # have its description silently ignored and a miscalculated
            # temperature put on the wire. Refuse instead. No bundled profile
            # can trip this; it is an authoring-time backstop.
            if spec.codec != "c256":
                raise ValidationError(
                    f"setpoint codec {spec.codec!r} is not the c256 encoding this "
                    "library writes; refusing"
                )

            # The profile's own limits are checked first so the more
            # specific, better-graded error is the one the caller sees when
            # both would apply. encode_setpoint_f then re-checks the
            # absolute ceiling unconditionally: with a correctly validated
            # profile that check can never fire, which is the point -- it is
            # the backstop if a profile ever carries a limit it should not.
            if not (profile.min_setpoint_f <= degf <= profile.max_setpoint_f):
                raise ValidationError(
                    f"setpoint {degf}F is outside this device's supported range "
                    f"{profile.min_setpoint_f}-{profile.max_setpoint_f}F"
                )
            word = c.encode_setpoint_f(degf)

            await self._refuse_if_fault_active()

            request = p.write_request(
                spec.block, spec.param, bytes([word >> 8, word & 0xFF])
            )
            await self._write_and_verify(request, spec.block, spec.param, (word,))

    async def async_set_mode(self, mode: Mode, duration_days: int = 0) -> None:
        """Set the operating mode. `duration_days=0` is only valid for the
        permanent modes (HYBRID, HEAT_PUMP); the timed modes require a
        non-zero duration, since duration=0 has never been observed for
        them and this library never sends an unobserved combination.

        The caller always states the duration explicitly; a duration read
        back from the device is never echoed into a write.
        """
        async with self._lock:
            if not self.is_connected or not self._session_ok or self._profile is None:
                await self.connect()
            assert self._profile is not None
            profile = self._profile

            spec = self._writable_spec(profile, "mode")

            # Membership in this profile's writable_modes, not merely "is a
            # known Mode value" -- a mode nobody has observed written on this
            # device must never reach the wire.
            if mode not in profile.writable_modes:
                raise ValidationError(
                    f"mode {mode!r} is not writable on this device "
                    f"(writable modes: {profile.writable_modes})"
                )
            # Structural, not left to caller discipline, and deliberately
            # independent of the check above: if a timed mode is ever added
            # to a profile's writable_modes, this rule must still hold.
            if mode in self._TIMED_MODES and duration_days == 0:
                raise ValidationError(
                    f"mode {mode!r} requires a non-zero duration; duration=0 "
                    "has never been observed for this mode and is never sent"
                )
            if mode not in self._TIMED_MODES and duration_days != 0:
                raise ValidationError(
                    f"mode {mode!r} is permanent; duration must be 0, got {duration_days}"
                )

            # Encode before anything touches the link: the codec
            # range-checks both halves of the word and raises
            # ValidationError, so an out-of-range duration is refused up
            # front rather than blowing up inside bytes() further down.
            mode_word = c.CODEC_REGISTRY["mode_word"].encode(
                c.ModeWord(duration_days=duration_days, mode=int(mode))
            )[0]

            await self._refuse_if_fault_active()

            request = p.write_request(
                spec.block, spec.param, bytes([duration_days, int(mode)])
            )
            await self._write_and_verify(request, spec.block, spec.param, (mode_word,))
