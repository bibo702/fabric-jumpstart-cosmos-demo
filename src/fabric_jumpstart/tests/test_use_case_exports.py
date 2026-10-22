import importlib.util
import json
from pathlib import Path
import re
import runpy
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "export_use_cases", ROOT / "tools" / "scripts" / "export-use-cases.py"
)
assert SPEC is not None and SPEC.loader is not None
exporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exporter
SPEC.loader.exec_module(exporter)


@pytest.fixture(scope="module")
def expected():
    return exporter.expected_files()


def test_all_versions_have_real_items_and_registration(expected):
    assert len(exporter.SNAPSHOTS) == 9
    for snapshot in exporter.SNAPSHOTS:
        prefix = Path(snapshot.scenario) / snapshot.version
        assert prefix / "registration.yml" in expected
        assert prefix / "README.md" in expected
        manifests = [
            data
            for path, data in expected.items()
            if path.is_relative_to(prefix) and path.name == ".platform"
        ]
        assert manifests
        for data in manifests:
            assert json.loads(data)["metadata"]["type"]
        if snapshot.app:
            assert prefix / "app" / "package-lock.json" in expected
            assert (
                prefix / "app" / "packages" / "frontend" / "src" / "App.tsx" in expected
            )


def test_exports_match_historical_sources_and_frozen_inventories(expected):
    for path, data in expected.items():
        assert (exporter.OUTPUT / path).read_bytes() == data, str(path)
    for snapshot in exporter.SNAPSHOTS:
        if snapshot.ref:
            inventory = json.loads(
                expected[
                    Path(snapshot.scenario) / snapshot.version / "snapshot-files.json"
                ]
            )
            assert inventory["source"] == "git"
            assert inventory["base_commit"] == snapshot.ref


@pytest.mark.parametrize(
    "name",
    [
        "app/.env",
        "app/.env.local",
        "app/.env.production",
        "app/.vscode/settings.json",
        "app/.mcp.json",
        "app/rayfin/.lockfile.json",
        "app/rayfin/.deployments.json",
        "app/rayfin/.env.secrets",
        "app/packages/functions/local.settings.json",
        "app/packages/functions/deploymentdata.json",
        "app/node_modules/example/index.js",
        "demo/__pycache__/notebook.pyc",
        "app/packages/frontend/dist/index.html",
        "app/.agents/skills/example/SKILL.md",
    ],
)
def test_local_settings_and_generated_state_are_excluded(name):
    assert not exporter.exportable(name)


@pytest.mark.parametrize(
    "name",
    [
        "demo/.platform",
        "demo/_provisioning/cosmos-definition.json",
        "app/configuration.example.json",
        "app/packages/functions/src/secrets.generated.ts",
        "app/package-lock.json",
    ],
)
def test_required_hidden_manifests_and_safe_configuration_are_included(name):
    assert exporter.exportable(name)


def test_overview_links_resolve():
    pages = [exporter.OUTPUT / "README.md", *exporter.OUTPUT.glob("*/README.md")]
    for page in pages:
        for target in re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (page.parent / target).exists(), (page, target)


@pytest.mark.parametrize("version", ["v0.3.0", "v0.3.1", "v0.3.2", "v0.4.0-unreleased"])
def test_exported_backend_artifacts_match_source_contract(version):
    root = exporter.OUTPUT / "cosmos-product-pim" / version / "cosmos-product-pim"
    builder = runpy.run_path(str(root / "build_artifacts.py"))
    for name, expected in builder["artifact_files"]().items():
        actual = (root / "ProductPimBackend.UserDataFunction" / name).read_bytes()
        if version == "v0.4.0-unreleased" or name.endswith(".whl"):
            assert actual == expected, (version, name)
        elif name.endswith((".json", ".platform")):
            assert json.loads(actual) == json.loads(expected), (version, name)
        else:
            assert actual.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n"), (
                version,
                name,
            )


def test_check_reports_missing_files_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "OUTPUT", tmp_path)
    monkeypatch.setattr(
        exporter, "expected_files", lambda _: {Path("demo/file.py"): b"pass\n"}
    )
    monkeypatch.setattr(sys, "argv", ["export-use-cases.py", "--check"])
    with pytest.raises(SystemExit, match="Out-of-date exports"):
        exporter.main()
    assert list(tmp_path.iterdir()) == []


def test_export_refuses_to_delete_obsolete_files(tmp_path, monkeypatch):
    extra = tmp_path / "obsolete.txt"
    extra.write_text("preserve me", encoding="utf-8")
    monkeypatch.setattr(exporter, "OUTPUT", tmp_path)
    monkeypatch.setattr(exporter, "expected_files", lambda _: {})
    monkeypatch.setattr(sys, "argv", ["export-use-cases.py"])
    with pytest.raises(SystemExit, match="Unexpected export files"):
        exporter.main()
    assert extra.read_text(encoding="utf-8") == "preserve me"


def test_frozen_snapshot_rejects_modified_content(tmp_path, monkeypatch):
    snapshot = exporter.SNAPSHOTS[0]
    folder = tmp_path / snapshot.scenario / snapshot.version
    folder.mkdir(parents=True)
    (folder / "snapshot-files.json").write_text(
        json.dumps({"files": {"file.txt": "incorrect-digest"}}), encoding="utf-8"
    )
    (folder / "file.txt").write_text("changed", encoding="utf-8")
    monkeypatch.setattr(exporter, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="Snapshot checksum mismatch"):
        exporter.frozen_files(snapshot)


def test_frozen_snapshot_rejects_path_traversal(tmp_path, monkeypatch):
    snapshot = exporter.SNAPSHOTS[0]
    folder = tmp_path / snapshot.scenario / snapshot.version
    folder.mkdir(parents=True)
    (folder / "snapshot-files.json").write_text(
        json.dumps({"files": {"../outside.txt": "digest"}}), encoding="utf-8"
    )
    monkeypatch.setattr(exporter, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="Invalid snapshot path"):
        exporter.frozen_files(snapshot)
