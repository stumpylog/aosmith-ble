from aosmith_ble.diagnostics import DiagnosticReport, probe_presence
from aosmith_ble.exceptions import ReadRefusedError, SessionError


class _FakeClientForProbe:
    """A tiny double exposing only what probe_presence calls -- not the real
    AOSmithBLEClient, since probe_presence only needs `_raw_read`."""

    def __init__(self, present_blocks: set[int]) -> None:
        self._present = present_blocks

    async def _raw_read(self, block: int, start: int, words: int) -> bytes:
        if block in self._present:
            return bytes.fromhex("0000")
        raise ReadRefusedError("not present")


async def test_probe_presence_reports_only_answering_blocks():
    client = _FakeClientForProbe(present_blocks={0, 2, 11})
    result = await probe_presence(client, max_block=15)
    assert result == ((0, 1), (2, 1), (11, 1))


async def test_probe_presence_treats_session_error_as_absent_too():
    class _Client(_FakeClientForProbe):
        async def _raw_read(self, block, start, words):
            if block == 5:
                raise SessionError("no session")
            return await super()._raw_read(block, start, words)

    client = _Client(present_blocks={0})
    result = await probe_presence(client, max_block=6)
    assert result == ((0, 1),)


def test_report_redacts_sensitive_fields_by_default():
    report = DiagnosticReport(
        model=b"HPTS-50",
        firmware=(6, 3),
        block_presence=((0, 1), (2, 1)),
        decoded_values={"asset_id": "02iQk000000EXAMPLE", "fault_code": 0},
    )
    markdown = report.to_markdown()
    assert "02iQk000000EXAMPLE" not in markdown
    assert "[REDACTED]" in markdown
    assert "fault_code" in markdown
    assert "0" in markdown


def test_report_reveals_sensitive_fields_when_opted_in():
    report = DiagnosticReport(
        model=b"HPTS-50",
        firmware=(6, 3),
        block_presence=(),
        decoded_values={"asset_id": "02iQk000000EXAMPLE"},
    )
    markdown = report.to_markdown(redact=False)
    assert "02iQk000000EXAMPLE" in markdown


def test_draft_profile_stanza_is_present_and_valid_python_syntax():
    report = DiagnosticReport(model=b"HPTS-50", firmware=(6, 4), block_presence=())
    stanza = report.draft_profile_stanza
    assert "Profile(" in stanza
    compile(
        stanza.replace("Profile(", "dict(").replace("Match(", "dict("),
        "<stanza>",
        "eval",
    )


def test_to_fixture_entries_passes_through_non_sensitive_captures():
    report = DiagnosticReport(
        model=b"HPTS-50",
        firmware=(6, 3),
        block_presence=((0, 1),),
        raw_entries=(
            {
                "id": "read_block0_start0_request",
                "hex": "bda0070b001a04",
                "source": "capture",
                "note": "captured during async_diagnose(): read_block0_start0 request",
            },
        ),
    )
    entries = report.to_fixture_entries()
    assert entries == [
        {
            "id": "read_block0_start0_request",
            "hex": "bda0070b001a04",
            "source": "capture",
            "note": "captured during async_diagnose(): read_block0_start0 request",
        },
    ]


def test_to_fixture_entries_passes_prebuilt_entries_through_unchanged():
    """`to_fixture_entries()` does no redaction of its own -- `raw_entries`
    arrives already redacted by `AOSmithBLEClient._build_raw_entries()` (see
    `tests/test_client_diagnose.py` for the real redaction test against
    live fixture data). This test only checks the pass-through contract."""
    raw_entries = (
        {
            "id": "init_response",
            "hex": "00" * 25,
            "source": "capture",
            "note": "redacted: init response carries the assetID",
        },
    )
    report = DiagnosticReport(
        model=None,
        firmware=None,
        block_presence=(),
        raw_entries=raw_entries,
    )
    entries = report.to_fixture_entries()
    assert entries == list(raw_entries)


def test_to_fixture_entries_defaults_to_empty():
    report = DiagnosticReport(model=None, firmware=None, block_presence=())
    assert report.to_fixture_entries() == []
