import aosmith_ble
from aosmith_ble.profiles.bundled import HPTS50_MODEL_BYTES


def test_package_importable_and_versioned():
    assert aosmith_ble.__version__ == "0.1.0"


def test_public_api_surface_is_importable():
    assert aosmith_ble.AOSmithBLEClient
    assert aosmith_ble.DeviceInfo
    assert aosmith_ble.Profile
    assert aosmith_ble.DiagnosticReport
    assert aosmith_ble.Mode.HYBRID == 4
    assert issubclass(aosmith_ble.ProtocolError, aosmith_ble.AOSmithError)
    assert issubclass(aosmith_ble.ReadRefusedError, aosmith_ble.ProtocolError)
    assert round(aosmith_ble.protocol.word_to_fahrenheit(0x331C), 1) == 124.0


def test_match_profile_is_reachable_from_the_public_surface():
    profile = aosmith_ble.match_profile(HPTS50_MODEL_BYTES, (6, 3))
    assert profile is not None
    assert profile.id == "hpts50-6.3"


def test_only_the_client_module_imports_bluetooth_machinery():
    """The package now depends on bleak, but only `client` may touch it.

    Everything else -- framing, codecs, profiles, models -- stays usable and
    unit-testable without a Bluetooth stack, so this walks the imports of
    every other module rather than checking the distribution's requirements.
    Imports are read from the parsed syntax tree, not matched as text, so a
    module that merely names bleak in a docstring or comment is not an
    offender.
    """
    import ast
    from pathlib import Path

    package_root = Path(aosmith_ble.__file__).parent
    offenders = []
    for path in sorted(package_root.rglob("*.py")):
        if path.name == "client.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(
                name.split(".")[0] == "bleak" or name.startswith("bleak_")
                for name in names
            ):
                offenders.append(path.relative_to(package_root).as_posix())
    assert offenders == []


def test_public_surface_exports_the_feature_model():
    assert aosmith_ble.Feature is not None
    assert aosmith_ble.FieldName is not None
    assert aosmith_ble.FieldScope is not None
    assert aosmith_ble.Trust is not None
    assert not hasattr(aosmith_ble, "HeaterState")


def test_version_is_0_1_0():
    assert aosmith_ble.__version__ == "0.1.0"
