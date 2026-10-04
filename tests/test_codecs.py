import pytest

from aosmith_ble.codecs import (
    ABSOLUTE_MAX_SETPOINT_F,
    CODEC_REGISTRY,
    ModeWord,
    encode_setpoint_f,
)
from aosmith_ble.exceptions import ValidationError


def test_absolute_ceiling_is_140():
    assert ABSOLUTE_MAX_SETPOINT_F == 140.0


def test_encode_setpoint_refuses_above_ceiling():
    with pytest.raises(ValidationError, match="140"):
        encode_setpoint_f(141.0)


def test_encode_setpoint_refuses_absurdly_low():
    with pytest.raises(ValidationError):
        encode_setpoint_f(10.0)


def test_encode_setpoint_accepts_known_verified_value():
    assert encode_setpoint_f(124.0) == 0x331C


def test_c256_round_trip():
    codec = CODEC_REGISTRY["c256"]
    word = codec.encode(124.0)
    assert word == (0x331C,)
    assert round(codec.decode(word), 1) == 124.0


def test_c256_encode_refuses_above_ceiling():
    codec = CODEC_REGISTRY["c256"]
    with pytest.raises(ValidationError):
        codec.encode(145.0)


def test_mode_word_round_trip():
    codec = CODEC_REGISTRY["mode_word"]
    encoded = codec.encode(ModeWord(duration_days=2, mode=1))
    assert encoded == (0x0201,)
    assert codec.decode(encoded) == ModeWord(duration_days=2, mode=1)


def test_mode_word_matches_captured_hybrid_permanent():
    # bd40080b0f000414 -> value bytes 00 04 -> duration=0, mode=4 (HYBRID)
    codec = CODEC_REGISTRY["mode_word"]
    assert codec.encode(ModeWord(0, 4)) == (0x0004,)


def test_mode_word_rejects_out_of_range_duration():
    codec = CODEC_REGISTRY["mode_word"]
    with pytest.raises(ValidationError):
        codec.encode(ModeWord(duration_days=1000, mode=1))


def test_u16_decodes_plain_word():
    codec = CODEC_REGISTRY["u16"]
    assert codec.decode((31,)) == 31


def test_u16_has_no_encoder():
    codec = CODEC_REGISTRY["u16"]
    with pytest.raises(ValidationError, match="no encoder"):
        codec.encode(31)


def test_ascii_swapped_decodes_known_model_string():
    # deswap_ascii is already tested at the protocol layer; this just
    # confirms the word-tuple -> bytes -> deswap plumbing is correct.
    codec = CODEC_REGISTRY["ascii_swapped"]
    # "PH" swapped into one big-endian word: 0x5048 -> deswaps to "HP"
    assert codec.decode((0x5048,)) == "HP"


def test_registry_has_exactly_the_five_bundled_codecs():
    assert set(CODEC_REGISTRY) == {"c256", "mode_word", "u16", "ascii_swapped", "fault"}
