"""Presence probing and the unknown-device diagnostic report.

Deliberately minimal reads: one word per block, never paging, rate limited,
bounded to block IDs 0-40. This is the only reader in the package allowed to
probe blocks a profile doesn't already describe, and it is never invoked
automatically -- only by an explicit diagnostics call.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .exceptions import ProtocolError, ReadRefusedError, SessionError

_PROBE_RATE_LIMIT_S = 0.2
_DEFAULT_MAX_BLOCK = 40
_MAX_CONSECUTIVE_TIMEOUTS = 3

# Fields whose raw values are sensitive enough to redact by default: the
# session credential, the full serial, and (if ever probed) a WiFi SSID
# range. The protocol has no secret otherwise, so publishing these is
# publishing control of the device to anyone in radio range.
_REDACTED_KEYS = frozenset({"asset_id", "serial", "ble_address", "wifi_ssid"})


async def probe_presence(
    client, max_block: int = _DEFAULT_MAX_BLOCK
) -> tuple[tuple[int, int], ...]:
    """Ask each block id in 0..max_block for exactly one word. A block that
    answers is present (word count recorded is always 1, since this probe
    never asks for more); a block that refuses is absent. Returns a sorted
    tuple of (block_id, word_count) pairs -- the fingerprint shape the
    matching system will use once fingerprinting ships."""
    present: list[tuple[int, int]] = []
    consecutive_timeouts = 0
    for block_id in range(max_block + 1):
        try:
            await client._raw_read(block_id, 0, 1)
        except (ReadRefusedError, SessionError):
            consecutive_timeouts = 0
            await asyncio.sleep(_PROBE_RATE_LIMIT_S)
            continue
        except ProtocolError:
            # A timeout (or any other malformed-reply failure) on an
            # unresponsive block -- treat it as absent like a refusal, but
            # cap how many of these in a row we tolerate so a fully silent
            # device doesn't take ~max_block timeouts (each one a full
            # `_timeout` wait) to finish the sweep.
            consecutive_timeouts += 1
            if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                break
            await asyncio.sleep(_PROBE_RATE_LIMIT_S)
            continue
        present.append((block_id, 1))
        consecutive_timeouts = 0
        await asyncio.sleep(_PROBE_RATE_LIMIT_S)
    return tuple(sorted(present))


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    model: bytes | None
    firmware: tuple[int, int] | None
    block_presence: tuple[tuple[int, int], ...]
    decoded_values: dict[str, object] = field(default_factory=dict)
    raw_entries: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @property
    def draft_profile_stanza(self) -> str:
        model_repr = self.model.decode(errors="replace") if self.model else "UNKNOWN"
        firmware_repr = self.firmware if self.firmware else "UNKNOWN"
        return (
            "Profile(\n"
            f'    id="{model_repr.strip().lower().replace(" ", "-") or "unknown"}-{firmware_repr}",\n'
            f"    match=Match(model={self.model!r}, firmware={self.firmware!r}),\n"
            "    min_setpoint_f=95, max_setpoint_f=130, allow_extended_max=False,\n"
            "    writable_modes=(),  # fill in only after an observed write\n"
            "    fields=(),  # fill in from the block presence below\n"
            ")"
        )

    def to_markdown(self, redact: bool = True) -> str:
        lines = ["# aosmith-ble diagnostic report", ""]
        lines.append(f"Model: {self.model!r}")
        lines.append(f"Firmware: {self.firmware}")
        lines.append("")
        lines.append("## Block presence")
        for block_id, words in self.block_presence:
            lines.append(f"- block {block_id}: {words} word(s) answered")
        lines.append("")
        lines.append("## Decoded values")
        for key, value in sorted(self.decoded_values.items()):
            if redact and key in _REDACTED_KEYS:
                lines.append(f"- {key}: [REDACTED]")
            else:
                lines.append(f"- {key}: {value!r}")
        lines.append("")
        lines.append("## Draft profile stanza")
        lines.append("```python")
        lines.append(self.draft_profile_stanza)
        lines.append("```")
        return "\n".join(lines)

    def to_fixture_entries(self) -> list[dict[str, str]]:
        """`tests/fixtures/frames.json`-shaped entries built from a
        preceding `async_diagnose()` call -- already redacted by whoever
        built `raw_entries` (see `AOSmithBLEClient._build_raw_entries`),
        this method exists so the two things that need this shape
        (`DiagnosticReport` itself, and any future consumer) have one place
        to get it from, matching `to_markdown`'s existing role for the
        human-readable report."""
        return list(self.raw_entries)
