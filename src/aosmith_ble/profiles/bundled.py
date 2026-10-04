"""The profile literals this library ships with.

Authored as plain Python so a malformed profile fails at import, not
mid-session -- see Profile.__post_init__ and FieldSpec.__post_init__.
"""

from __future__ import annotations

from ..const import Mode
from . import FieldName, FieldScope, FieldSpec, Match, Profile, Trust, resolve_inherits

# Raw wire bytes for the model field (params 16-19, 8 bytes/4 words) --
# matching happens on these raw bytes, never on the deswapped string (see
# the "Identification and matching" note above this profile literal).
# This is the byte-pair swap of b"HPTS-50\x00": the documented deswap of
# this field is exactly "HPTS-50" with no trailing space, and a space
# would have survived deswap_ascii's printable-byte filter if it were
# there, so the padding byte is non-printable (0x00). Confirmed against a
# real Block 0 read on 2026-09-13 (docs/protocol/blocks.md, Block 0).
HPTS50_MODEL_BYTES = bytes.fromhex("50485354352d0030")

_HPTS50_6_3 = Profile(
    id="hpts50-6.3",
    match=Match(model=HPTS50_MODEL_BYTES, firmware=(6, 3)),
    min_setpoint_f=95,
    max_setpoint_f=130,
    allow_extended_max=False,
    writable_modes=(Mode.HYBRID, Mode.HEAT_PUMP, Mode.ELECTRIC, Mode.VACATION),
    fields=(
        (
            FieldName.SETPOINT,
            FieldSpec(
                block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
            ),
        ),
        (
            FieldName.MODE,
            FieldSpec(
                block=11,
                param=15,
                words=1,
                codec="mode_word",
                read=Trust.OK,
                write=Trust.OK,
            ),
        ),
        (
            FieldName.FAULT,
            FieldSpec(block=2, param=7, words=1, codec="fault", read=Trust.OK),
        ),
        (
            FieldName.MODEL,
            FieldSpec(
                block=0,
                param=16,
                words=4,
                codec="ascii_swapped",
                read=Trust.OK,
                scope=FieldScope.IDENTITY,
            ),
        ),
        (
            FieldName.SERIAL,
            FieldSpec(
                block=0,
                param=36,
                words=5,
                codec="ascii_swapped",
                read=Trust.PARTIAL,
                scope=FieldScope.IDENTITY,
            ),
        ),
        (
            FieldName.VACATION_DAYS_REMAINING,
            FieldSpec(block=11, param=17, words=1, codec="u16", read=Trust.OK),
        ),
        (
            FieldName.GUEST_DAYS_REMAINING,
            FieldSpec(block=11, param=18, words=1, codec="u16", read=Trust.UNVERIFIED),
        ),
        (
            FieldName.ELECTRIC_DAYS_REMAINING,
            FieldSpec(block=11, param=19, words=1, codec="u16", read=Trust.OK),
        ),
    ),
)

_REGISTRY = {"hpts50-6.3": _HPTS50_6_3}

BUNDLED_PROFILES: dict[str, Profile] = {
    profile_id: resolve_inherits(_REGISTRY, profile_id) for profile_id in _REGISTRY
}


def match_profile(model: bytes, firmware: tuple[int, int]) -> Profile | None:
    """Exact match on (model, firmware) only -- fingerprint-based matching
    is not implemented yet (it needs block-length detection this project
    doesn't have). No match returns None; the caller is responsible for
    refusing the device and producing a diagnostic report."""
    for profile in BUNDLED_PROFILES.values():
        if profile.match is None:
            continue
        if profile.match.model == model and profile.match.firmware == firmware:
            return profile
    return None
