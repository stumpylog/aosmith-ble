"""Named value codecs, resolved through a closed registry.

A `Profile`'s `FieldSpec.codec` references one of these by name -- never a
callable directly, and never through a plugin/entry-point mechanism. Keeping
the registry closed means every codec a profile can possibly use is defined
here, in one auditable place, matching the safety model's refusal to let a
raw or unvalidated write path exist anywhere in the package.

`protocol.py` stays free of any notion of "profile" or "field" -- it only
knows about frames and raw words. This module is the adapter layer between
that pure wire format and the named, per-profile field model in `profiles/`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Protocol, runtime_checkable

from . import protocol as p
from .exceptions import ValidationError

if TYPE_CHECKING:
    from .models import Fault

# The manufacturer's own app never writes above 140F, and this project has
# never written above 126F on the wire. This ceiling is independent of any
# profile -- a profile's own maximum can only be lower, never higher, and
# any profile-gated write path must check this ceiling too, regardless of
# what a profile permits.
ABSOLUTE_MAX_SETPOINT_F = 140.0
ABSOLUTE_MIN_SETPOINT_F = 32.0  # the codec's floor; profiles set a tighter one


def encode_setpoint_f(degf: float) -> int:
    """Encode a Fahrenheit setpoint as a wire word, refusing outside the
    absolute hard ceiling. This check is unconditional and profile-blind --
    it exists so that no caller, including a future one that bypasses a
    profile's own limits by mistake, can ever encode a setpoint outside the
    range the manufacturer's own app permits."""
    if not (ABSOLUTE_MIN_SETPOINT_F <= degf <= ABSOLUTE_MAX_SETPOINT_F):
        raise ValidationError(
            f"setpoint {degf}F is outside the absolute range "
            f"{ABSOLUTE_MIN_SETPOINT_F}-{ABSOLUTE_MAX_SETPOINT_F}F"
        )
    return p.fahrenheit_to_word(degf)


class ModeWord(NamedTuple):
    duration_days: int
    mode: int


def _decode_mode_word(words: tuple[int, ...]) -> ModeWord:
    (word,) = words
    return ModeWord(duration_days=word >> 8, mode=word & 0xFF)


def _encode_mode_word(value: ModeWord) -> tuple[int, ...]:
    if not (0 <= value.duration_days <= 0xFF):
        raise ValidationError(f"duration_days {value.duration_days} out of range 0-255")
    if not (0 <= value.mode <= 0xFF):
        raise ValidationError(f"mode {value.mode} out of range 0-255")
    return ((value.duration_days << 8) | value.mode,)


def _decode_c256(words: tuple[int, ...]) -> float:
    """Decode a Celsius*256 word as degrees Fahrenheit (the unit this
    library's models and callers use throughout; the wire format's own unit
    is what the codec's name records, not what it hands back)."""
    (word,) = words
    return p.word_to_fahrenheit(word)


def _encode_c256(degf: float) -> tuple[int, ...]:
    return (encode_setpoint_f(degf),)


def _decode_u16(words: tuple[int, ...]) -> int:
    (word,) = words
    return word


def _decode_ascii_swapped(words: tuple[int, ...]) -> str:
    payload = b"".join(w.to_bytes(2, "big") for w in words)
    return p.deswap_ascii(payload)


def _decode_fault(words: tuple[int, ...]) -> Fault:
    from .models import Fault  # local import: models imports profiles, which
    # codecs must not depend on, to avoid a cycle

    (word,) = words
    return Fault(code=word)


@runtime_checkable
class Codec(Protocol):
    def decode(self, words: tuple[int, ...]) -> object: ...
    def encode(
        self, value: object
    ) -> tuple[int, ...]: ...  # optional; see NoEncodeCodec


class _FunctionCodec:
    """Wraps a decode function and an optional encode function as a Codec."""

    def __init__(self, name: str, decode, encode=None) -> None:
        self._name = name
        self._decode = decode
        self._encode = encode

    def decode(self, words: tuple[int, ...]) -> object:
        return self._decode(words)

    def encode(self, value: object) -> tuple[int, ...]:
        if self._encode is None:
            raise ValidationError(
                f"codec {self._name!r} has no encoder (read-only field)"
            )
        return self._encode(value)


CODEC_REGISTRY: dict[str, Codec] = {
    "c256": _FunctionCodec("c256", _decode_c256, _encode_c256),
    "mode_word": _FunctionCodec("mode_word", _decode_mode_word, _encode_mode_word),
    "u16": _FunctionCodec("u16", _decode_u16),
    "ascii_swapped": _FunctionCodec("ascii_swapped", _decode_ascii_swapped),
    "fault": _FunctionCodec("fault", _decode_fault),
}
