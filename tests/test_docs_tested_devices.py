"""Keeps docs/tested-devices.md in step with the bundled profiles.

The page embeds a table per profile. This test rebuilds each table from
BUNDLED_PROFILES and requires it to appear verbatim in the page, so changing a
profile without updating the docs (or the reverse) fails loudly.
"""

from pathlib import Path

from aosmith_ble.profiles import Trust
from aosmith_ble.profiles.bundled import BUNDLED_PROFILES

PAGE = Path(__file__).parent.parent / "docs" / "tested-devices.md"


def _grade(trust: Trust) -> str:
    return "-" if trust is Trust.UNSUPPORTED else trust.value


def render_fields_table(profile) -> str:
    rows = [
        "| Field | Location | Read | Write |",
        "| --- | --- | --- | --- |",
    ]
    for name, spec in profile.fields:
        location = f"block {spec.block}, param {spec.param}"
        rows.append(
            f"| `{name.value}` | {location} | {_grade(spec.read)} | {_grade(spec.write)} |"
        )
    return "\n".join(rows)


def render_limits(profile) -> str:
    modes = ", ".join(mode.name for mode in profile.writable_modes)
    return (
        f"Setpoint writes: {profile.min_setpoint_f:g} to {profile.max_setpoint_f:g} F. "
        f"Writable modes: {modes}."
    )


def test_page_exists():
    assert PAGE.is_file()


def test_every_bundled_profile_is_documented():
    page = PAGE.read_text()
    for profile_id, profile in BUNDLED_PROFILES.items():
        assert f"`{profile_id}`" in page, f"{profile_id} missing from tested-devices.md"
        assert render_fields_table(profile) in page, (
            f"{profile_id} field table is stale"
        )
        assert render_limits(profile) in page, f"{profile_id} limits line is stale"


def test_documented_match_equals_profile_match():
    page = PAGE.read_text()
    for profile in BUNDLED_PROFILES.values():
        major, minor = profile.match.firmware
        assert f"{major}.{minor}" in page
