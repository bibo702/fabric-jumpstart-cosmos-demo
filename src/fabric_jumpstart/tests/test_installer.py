"""Tests for repo_ref override in JumpstartInstaller."""

import base64
import json
from unittest.mock import patch, MagicMock
from fabric_jumpstart.installer import JumpstartInstaller
from fabric_jumpstart.utils import clone_files_to_temp_directory, update_docs_uri_with_ref


def _make_config(**overrides):
    """Return a minimal jumpstart config dict."""
    config = {
        "id": 1,
        "logical_id": "test-jumpstart",
        "source": {
            "repo_url": "https://github.com/example/repo.git",
            "repo_ref": "v1.0.0",
            "workspace_path": "demo/",
        },
    }
    config.update(overrides)
    return config


def test_clone_files_to_temp_directory_ignores_python_bytecode(tmp_path):
    source = tmp_path / "source"
    cache = source / "item" / "__pycache__"
    cache.mkdir(parents=True)
    (source / "item" / "function_app.py").write_text("value = 1", encoding="utf-8")
    (cache / "function_app.cpython-312.pyc").write_bytes(b"compiled")

    destination = clone_files_to_temp_directory(source)

    assert (destination / "item" / "function_app.py").is_file()
    assert not (destination / "item" / "__pycache__").exists()


@patch("fabric_jumpstart.installer.clone_repository")
def test_prepare_workspace_uses_config_repo_ref_by_default(mock_clone):
    """Without repo_ref kwarg, the registered config value is used."""
    mock_clone.return_value = MagicMock()
    installer = JumpstartInstaller(_make_config(), workspace_id="ws-123", instance_name="js")
    installer.prepare_workspace()

    mock_clone.assert_called_once()
    _, kwargs = mock_clone.call_args
    assert kwargs["ref"] == "v1.0.0"


@patch("fabric_jumpstart.installer.clone_repository")
def test_prepare_workspace_uses_repo_ref_override(mock_clone):
    """When repo_ref kwarg is provided, it overrides the config value."""
    mock_clone.return_value = MagicMock()
    installer = JumpstartInstaller(
        _make_config(), workspace_id="ws-123", instance_name="js", repo_ref="v2.0.0-beta"
    )
    installer.prepare_workspace()

    mock_clone.assert_called_once()
    _, kwargs = mock_clone.call_args
    assert kwargs["ref"] == "v2.0.0-beta"


def test_effective_docs_uri_returns_original_when_no_override():
    """Without repo_ref override, effective_docs_uri returns the original."""
    config = _make_config(jumpstart_docs_uri="https://github.com/example/repo/blob/v1.0.0/README.md")
    installer = JumpstartInstaller(config, workspace_id="ws-123", instance_name="js")
    assert installer.effective_docs_uri == "https://github.com/example/repo/blob/v1.0.0/README.md"


def test_effective_docs_uri_updates_github_blob_url_with_override():
    """When repo_ref override is provided, GitHub blob URLs are updated."""
    config = _make_config(jumpstart_docs_uri="https://github.com/example/repo/blob/v1.0.0/README.md")
    installer = JumpstartInstaller(
        config, workspace_id="ws-123", instance_name="js", repo_ref="v2.0.0"
    )
    assert installer.effective_docs_uri == "https://github.com/example/repo/blob/v2.0.0/README.md"


def test_effective_docs_uri_preserves_non_github_urls():
    """Non-GitHub URLs are returned unchanged even with repo_ref override."""
    config = _make_config(jumpstart_docs_uri="https://jumpstart.fabric.microsoft.com/docs/")
    installer = JumpstartInstaller(
        config, workspace_id="ws-123", instance_name="js", repo_ref="v2.0.0"
    )
    assert installer.effective_docs_uri == "https://jumpstart.fabric.microsoft.com/docs/"


def test_effective_docs_uri_handles_empty_string():
    """Empty docs_uri is returned unchanged."""
    config = _make_config(jumpstart_docs_uri="")
    installer = JumpstartInstaller(
        config, workspace_id="ws-123", instance_name="js", repo_ref="v2.0.0"
    )
    assert installer.effective_docs_uri == ""


def test_effective_docs_uri_handles_none():
    """None docs_uri is returned unchanged."""
    config = _make_config()  # No jumpstart_docs_uri
    installer = JumpstartInstaller(
        config, workspace_id="ws-123", instance_name="js", repo_ref="v2.0.0"
    )
    assert installer.effective_docs_uri is None


def test_provision_cosmos_database_creates_item_and_injects_settings(tmp_path):
    logical_root = tmp_path / "test-jumpstart"
    definition_path = logical_root / "_provisioning" / "cosmos-definition.json"
    definition_path.parent.mkdir(parents=True)
    definition = {"containers": [{"resource": {"id": "SampleData"}}]}
    definition_path.write_text(json.dumps(definition), encoding="utf-8")
    function_path = logical_root / "PriceWriteback.UserDataFunction" / "function_app.py"
    function_path.parent.mkdir()
    function_path.write_text(
        'URI = "{my-cosmos-artifact-uri}"\nDB = "{my-cosmos-database-name}"\n',
        encoding="utf-8",
    )

    config = _make_config(
        cosmos_database={
            "display_name": "cosmos db jumpstart",
            "definition_path": "_provisioning/cosmos-definition.json",
        }
    )
    installer = JumpstartInstaller(config, workspace_id="ws-123", instance_name="js")
    installer.temp_workspace_path = tmp_path
    endpoint = MagicMock()

    def invoke(*, method, url, body=None):
        if method == "GET" and url.endswith("/items"):
            return {"body": {"value": []}, "status_code": 200}
        if method == "POST" and url.endswith("/cosmosDbDatabases"):
            encoded = body["definition"]["parts"][0]["payload"]
            assert json.loads(base64.b64decode(encoded)) == definition
            assert body["displayName"] == "demo_cosmos db jumpstart"
            return {"body": {"id": "cosmos-123"}, "status_code": 201}
        if method == "GET" and url.endswith("/cosmosDbDatabases/cosmos-123"):
            return {
                "body": {"properties": {"serverFqdn": "cosmos-123.cosmos.fabric.microsoft.com"}},
                "status_code": 200,
            }
        raise AssertionError(f"Unexpected call: {method} {url}")

    endpoint.invoke.side_effect = invoke
    workspace = MagicMock(endpoint=endpoint)
    installer.workspace_manager = MagicMock()
    installer.workspace_manager.get_fabric_workspace.return_value = workspace

    result = installer.provision_cosmos_database("demo_")

    assert result == "https://cosmos-123.cosmos.fabric.microsoft.com"
    assert function_path.read_text(encoding="utf-8") == (
        'URI = "https://cosmos-123.cosmos.fabric.microsoft.com"\n'
        'DB = "demo_cosmos db jumpstart"\n'
    )


# Tests for update_docs_uri_with_ref utility function

def test_update_docs_uri_with_ref_basic():
    """Basic replacement of ref in GitHub blob URL."""
    result = update_docs_uri_with_ref(
        "https://github.com/microsoft/repo/blob/v1.0.0/README.md",
        "v1.0.0",
        "v2.0.0"
    )
    assert result == "https://github.com/microsoft/repo/blob/v2.0.0/README.md"


def test_update_docs_uri_with_ref_same_ref():
    """Returns original when refs are the same."""
    original = "https://github.com/microsoft/repo/blob/v1.0.0/README.md"
    result = update_docs_uri_with_ref(original, "v1.0.0", "v1.0.0")
    assert result == original


def test_update_docs_uri_with_ref_non_github():
    """Non-GitHub URLs are unchanged."""
    original = "https://docs.example.com/readme"
    result = update_docs_uri_with_ref(original, "v1.0.0", "v2.0.0")
    assert result == original


def test_update_docs_uri_with_ref_github_without_blob():
    """GitHub URLs without /blob/ are unchanged."""
    original = "https://github.com/microsoft/repo"
    result = update_docs_uri_with_ref(original, "v1.0.0", "v2.0.0")
    assert result == original


def test_update_docs_uri_with_ref_ref_not_in_url():
    """Returns original if the original ref is not in the URL."""
    original = "https://github.com/microsoft/repo/blob/main/README.md"
    result = update_docs_uri_with_ref(original, "v1.0.0", "v2.0.0")
    assert result == original
