from aosmith_ble.protocol import fahrenheit_to_word, word_to_celsius, word_to_fahrenheit

# (degF, word) pairs, each independently recomputed from
# round((degF - 32) / 1.8 * 256) and cross-checked against a captured or
# hardware-verified write frame.
KNOWN_PAIRS = [
    (120.0, 0x30E4),
    (124.0, 0x331C),
    (126.0, 0x3439),
    (114.0, 0x2D8E),
]


def test_fahrenheit_to_word_known_pairs():
    for degf, word in KNOWN_PAIRS:
        assert fahrenheit_to_word(degf) == word


def test_word_to_fahrenheit_known_pairs():
    for degf, word in KNOWN_PAIRS:
        assert round(word_to_fahrenheit(word), 1) == degf


def test_word_to_celsius_is_word_over_256():
    assert word_to_celsius(0x331C) == 0x331C / 256.0


def test_round_trip_is_stable():
    for degf, _word in KNOWN_PAIRS:
        assert round(word_to_fahrenheit(fahrenheit_to_word(degf)), 1) == degf
