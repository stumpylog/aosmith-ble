"""Pure protocol layer: frame construction and parsing, no I/O.

Deliberately free of any Bluetooth dependency so it can be unit-tested against
captured frames without hardware, and reused from a different transport.
"""

from __future__ import annotations

import hashlib
import hmac

from .const import (
    ASSET_ID_LEN,
    BLOCK2_CURRENT_FAULT_ERROR_CODE,
    Block,
    Cmd,
    HDR_REQUEST,
    HDR_RESPONSE,
    STATUS_OK,
    STATUS_REFUSED,
)
from .crc import check, frame
from .exceptions import ProtocolError, ReadRefusedError, SessionError

# -- Temperature -----------------------------------------------------------
# word = round((degF - 32) / 1.8 * 256); the inverse recovers degF via
# word / 256 * 1.8 + 32. Verified against every setpoint write observed on
# the wire (120F/124F/126F/114F) and against a hardware round trip.


def word_to_fahrenheit(word: int) -> float:
    return word / 256.0 * 1.8 + 32.0


def word_to_celsius(word: int) -> float:
    return word / 256.0


def fahrenheit_to_word(degf: float) -> int:
    return round((degf - 32.0) / 1.8 * 256.0)


# -- Requests ----------------------------------------------------------


def write_request(block: int, param: int, value: bytes) -> bytes:
    """0x40 -- write one parameter. Length byte is len(value) + 6."""
    return frame(
        bytes([HDR_REQUEST, Cmd.WRITE_BLOCK, len(value) + 6, block, param]) + value
    )


def set_setpoint_request(degf: float) -> bytes:
    word = fahrenheit_to_word(degf)
    return write_request(Block.CONTROL, 0, bytes([word >> 8, word & 0xFF]))


def set_mode_request(mode: int, duration_days: int = 0) -> bytes:
    """Mode value is ``<duration_days> <mode>``; duration 0 means permanent."""
    return write_request(Block.CONTROL, 15, bytes([duration_days, mode]))


# -- Session handshake -------------------------------------------------


def init_request(slot: int = 1) -> bytes:
    """0xF2 -- read a pairing slot; the response carries the assetID."""
    return frame(bytes([HDR_REQUEST, Cmd.INIT, 0x05, slot]))


def challenge_request() -> bytes:
    """0xF4 -- ask for this session's 2-byte nonce."""
    return frame(bytes([HDR_REQUEST, Cmd.CHALLENGE_REQUEST, 0x04]))


def challenge_response(challenge: bytes, asset_id: bytes) -> bytes:
    """0xF1 -- HMAC-SHA1 over the assetID, keyed with the challenge.

    Note the inversion: the nonce is the *key* and the assetID is the
    *message*, not the other way round.
    """
    if len(challenge) != 2:
        raise ProtocolError(f"challenge must be 2 bytes, got {len(challenge)}")
    if len(asset_id) != ASSET_ID_LEN:
        raise ProtocolError(
            f"assetID must be {ASSET_ID_LEN} bytes, got {len(asset_id)}"
        )
    digest = hmac.new(challenge, asset_id, hashlib.sha1).digest()
    return frame(bytes([HDR_REQUEST, Cmd.CHALLENGE_RESPONSE, 0x19, 0x01]) + digest)


def _validate(rsp: bytes, min_len: int) -> None:
    if len(rsp) < min_len:
        raise ProtocolError(f"response too short: {rsp.hex(' ')}")
    if rsp[0] != HDR_RESPONSE:
        raise ProtocolError(f"bad response header: {rsp.hex(' ')}")
    if not check(rsp):
        raise ProtocolError(f"CRC mismatch: {rsp.hex(' ')}")


def parse_init(rsp: bytes) -> tuple[int, bytes]:
    """Return ``(slot_status, asset_id)``.

    ``slot_status`` is 0x01 when the pairing slot is populated and the
    assetID is meaningful, 0x00 when the slot is empty and the field is
    zeroed.
    """
    _validate(rsp, 24)
    return rsp[3], bytes(rsp[4 : 4 + ASSET_ID_LEN])


def parse_challenge(rsp: bytes) -> bytes:
    """Return the 2-byte session nonce from a 0xF4 response."""
    _validate(rsp, 7)
    return bytes(rsp[3:5])


def challenge_accepted(rsp: bytes) -> bool:
    """0x80 means the challenge response was accepted."""
    _validate(rsp, 5)
    return rsp[3] == STATUS_OK


# -- Reads, write acks, and the refusal path ----------------------------


def read_request(block: int, start_param: int, words: int) -> bytes:
    """0xA0 -- read ``words`` 2-byte parameters starting at ``start_param``.

    The device caps a response at MAX_WORDS_PER_READ; page with ``start_param``.
    """
    return frame(bytes([HDR_REQUEST, Cmd.READ_BLOCK, 0x07, block, start_param, words]))


def fault_read_request() -> bytes:
    return read_request(Block.FAULTS, BLOCK2_CURRENT_FAULT_ERROR_CODE, 1)


def write_accepted(rsp: bytes, block: int, param_idx: int) -> bool:
    """A write ack is ``DB 02 07 <block> <param> 80 <crc>``."""
    _validate(rsp, 7)
    return rsp[3] == block and rsp[4] == param_idx and rsp[5] == STATUS_OK


def parse_read(
    rsp: bytes,
    *,
    request_block: int,
    request_start: int,
    request_words: int,
) -> bytes:
    """Return the parameter payload of a read response.

    Both 7-byte short-response shapes carry a non-``STATUS_OK`` byte at the
    status position, but mean different things and call for different
    recovery -- see ``ReadRefusedError`` and ``SessionError``'s docstrings.
    The caller's own request parameters are required to tell them apart: the
    session-not-established shape echoes them back instead of using a fixed
    value.
    """
    _validate(rsp, 7)
    status = rsp[-2]
    if status != STATUS_OK:
        if len(rsp) == 7 and status == STATUS_REFUSED:
            raise ReadRefusedError(
                f"block {request_block} refused at start {request_start}: "
                f"{rsp.hex(' ')}"
            )
        if (
            len(rsp) == 7
            and rsp[3] == request_block
            and rsp[4] == request_start
            and rsp[5] == request_words
        ):
            raise SessionError(
                "read echoed the request instead of a status byte; the "
                f"session challenge has not been accepted: {rsp.hex(' ')}"
            )
        raise ProtocolError(
            f"read refused (status 0x{status:02X}); "
            f"session may not be established: {rsp.hex(' ')}"
        )
    if len(rsp) < 8:
        raise ProtocolError(f"read response has no payload: {rsp.hex(' ')}")
    if rsp[3] != request_block or rsp[4] != request_start:
        raise ProtocolError(
            f"read response echoed block={rsp[3]} start={rsp[4]}, "
            f"expected block={request_block} start={request_start} "
            f"(stale or mismatched reply): {rsp.hex(' ')}"
        )
    return bytes(rsp[5:-2])


def param(payload: bytes, index: int) -> int:
    """Parameter ``index`` as a big-endian uint16 from a read payload."""
    off = index * 2
    if off + 1 >= len(payload):
        raise ProtocolError(
            f"param {index} beyond payload of {len(payload) // 2} words"
        )
    return (payload[off] << 8) | payload[off + 1]


def word_count(payload: bytes) -> int:
    return len(payload) // 2


# -- ASCII deswap and the unsolicited-AT-command guard -------------------


def deswap_ascii(payload: bytes) -> str:
    """Decode ASCII stored byte-swapped within each 16-bit word.

    Block 0 holds the model and serial this way.
    """
    out = bytearray()
    for i in range(0, len(payload) - 1, 2):
        out += bytes([payload[i + 1], payload[i]])
    return "".join(chr(b) if 32 <= b < 127 else "" for b in out)


def is_at_command(data: bytes) -> bool:
    """True if a notification is an unsolicited AT command, not a protocol frame.

    The BLE-to-serial bridge chip in the device occasionally leaks a raw AT
    command (e.g. ``AT+RESET=1``) onto the notification channel, most often
    around a reset. It must be dropped rather than mistaken for the reply to
    an outstanding request.
    """
    return len(data) >= 3 and data[0:1] == b"A" and data[1:2] == b"T"
