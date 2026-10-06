"""Tests for token credential resolution via environment variable."""

import base64
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from fabric_jumpstart.utils import (
    CREDENTIAL_OVERRIDE_ENV_VAR,
    _decode_jwt,
    _generate_fabric_credential,
    _get_notebookutils_credentials,
    _is_fabric_runtime,
    resolve_token_credential,
)


def _make_mock_jwt(claims=None):
    """Create a mock JWT token string with the given claims."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps(claims or {"exp": 9999999999}).encode()
    ).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(b"signature").decode().rstrip("=")
    return f"{header}.{payload}.{signature}"


class TestResolveTokenCredential:
    """Tests for resolve_token_credential()."""

    @patch("fabric_jumpstart.utils._is_fabric_runtime", return_value=False)
    @patch("fabric_jumpstart.utils.DefaultAzureCredential", create=True)
    def test_returns_default_credential_when_env_var_unset(self, mock_dac_cls, mock_runtime):
        """No env var and not in Fabric → DefaultAzureCredential."""
        mock_instance = MagicMock()
        mock_dac_cls.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            with patch("azure.identity.DefaultAzureCredential", mock_dac_cls):
                result = resolve_token_credential()

        assert result is mock_instance

    @patch("fabric_jumpstart.utils._is_fabric_runtime", return_value=False)
    @patch("fabric_jumpstart.utils.DefaultAzureCredential", create=True)
    def test_returns_default_credential_when_env_var_empty(self, mock_dac_cls, mock_runtime):
        """Empty env var → DefaultAzureCredential."""
        mock_instance = MagicMock()
        mock_dac_cls.return_value = mock_instance

        with patch.dict(os.environ, {CREDENTIAL_OVERRIDE_ENV_VAR: ""}):
            with patch("azure.identity.DefaultAzureCredential", mock_dac_cls):
                result = resolve_token_credential()

        assert result is mock_instance

    @patch("fabric_jumpstart.utils._is_fabric_runtime", return_value=True)
    @patch("fabric_jumpstart.utils._generate_fabric_credential")
    def test_returns_fabric_credential_in_fabric_runtime(self, mock_gen, mock_runtime):
        """In Fabric runtime without env var → FabricTokenCredential."""
        mock_cred = MagicMock()
        mock_gen.return_value = mock_cred

        with patch.dict(os.environ, {}, clear=True):
            result = resolve_token_credential()

        mock_gen.assert_called_once()
        assert result is mock_cred

    def test_returns_azure_cli_credential(self):
        """AzureCliCredential env var → instantiated credential."""
        mock_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.AzureCliCredential = mock_cls

        with patch.dict(os.environ, {CREDENTIAL_OVERRIDE_ENV_VAR: "AzureCliCredential"}):
            with patch("importlib.import_module", return_value=mock_module) as mock_import:
                result = resolve_token_credential()

        mock_import.assert_called_once_with("azure.identity")
        mock_cls.assert_called_once_with()
        assert result is mock_cls.return_value

    def test_returns_managed_identity_credential(self):
        """ManagedIdentityCredential env var → instantiated credential."""
        mock_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.ManagedIdentityCredential = mock_cls

        with patch.dict(os.environ, {CREDENTIAL_OVERRIDE_ENV_VAR: "ManagedIdentityCredential"}):
            with patch("importlib.import_module", return_value=mock_module):
                result = resolve_token_credential()

        mock_cls.assert_called_once_with()
        assert result is mock_cls.return_value

    def test_raises_on_unsupported_value(self):
        """Unknown credential name → ValueError."""
        with patch.dict(os.environ, {CREDENTIAL_OVERRIDE_ENV_VAR: "BogusCredential"}):
            with pytest.raises(ValueError, match="Unsupported.*BogusCredential"):
                resolve_token_credential()


class TestDecodeJwt:
    """Tests for _decode_jwt()."""

    def test_decode_valid_jwt(self):
        """Valid JWT → decoded payload dict."""
        claims = {"exp": 9999999999, "upn": "user@example.com"}
        token = _make_mock_jwt(claims)
        result = _decode_jwt(token)
        assert result["exp"] == 9999999999
        assert result["upn"] == "user@example.com"

    def test_decode_invalid_jwt_format(self):
        """Invalid JWT format → ValueError."""
        with pytest.raises(ValueError, match="invalid JWT format"):
            _decode_jwt("not.a.valid.jwt.token")

    def test_decode_two_part_token(self):
        """Two-part token → ValueError."""
        with pytest.raises(ValueError, match="invalid JWT format"):
            _decode_jwt("header.payload")


class TestFabricRuntimeDetection:
    """Tests for capability-based Fabric runtime detection."""

    def test_detects_credentials_on_notebookutils_root(self):
        """A callable getToken API identifies a supported Fabric runtime."""
        mock_notebookutils = MagicMock()

        with patch("importlib.import_module", return_value=mock_notebookutils):
            assert _is_fabric_runtime() is True

    def test_returns_false_when_notebookutils_is_unavailable(self):
        """A regular Python environment is not treated as Fabric."""
        with patch("importlib.import_module", side_effect=ImportError):
            assert _is_fabric_runtime() is False

    def test_imports_credentials_submodule_when_not_on_root(self):
        """The credentials submodule can be loaded even when not exposed on root."""
        mock_notebookutils = MagicMock(spec=[])
        mock_credentials = MagicMock()

        with patch(
            "importlib.import_module",
            side_effect=[mock_notebookutils, mock_credentials],
        ) as mock_import:
            result = _get_notebookutils_credentials()

        assert result is mock_credentials
        assert mock_import.call_args_list[1].args == ("notebookutils.credentials",)

    def test_raises_for_legacy_fabric_runtime(self):
        """NotebookUtils without getToken produces an actionable runtime error."""
        mock_notebookutils = MagicMock(spec=[])

        with patch(
            "importlib.import_module",
            side_effect=[mock_notebookutils, ImportError],
        ):
            with pytest.raises(RuntimeError, match="Runtime 2.0 or later"):
                _is_fabric_runtime()


class TestGenerateFabricCredential:
    """Tests for _generate_fabric_credential()."""

    def test_credential_returns_token_with_expiration(self):
        """Credential get_token() returns AccessToken with JWT expiration."""
        mock_jwt = _make_mock_jwt({"exp": 9999999999})
        mock_credentials = MagicMock()
        mock_credentials.getToken.return_value = mock_jwt

        with patch(
            "fabric_jumpstart.utils._get_notebookutils_credentials",
            return_value=mock_credentials,
        ):
            credential = _generate_fabric_credential()
            token = credential.get_token()

        assert token.token == mock_jwt
        assert token.expires_on == 9999999999
        mock_credentials.getToken.assert_called_once_with("pbi")

    def test_credential_fallback_expiration(self):
        """When JWT parsing fails, uses fallback expiration (~1 hour)."""
        mock_credentials = MagicMock()
        mock_credentials.getToken.return_value = "invalid.jwt.token"

        with patch(
            "fabric_jumpstart.utils._get_notebookutils_credentials",
            return_value=mock_credentials,
        ):
            credential = _generate_fabric_credential()
            current_time = int(time.time())
            token = credential.get_token()

        assert token.expires_on >= current_time + 3500
        assert token.expires_on <= current_time + 3700


class TestWorkspaceManagerCredentialPassthrough:
    """Ensure WorkspaceManager passes resolved credential to FabricWorkspace."""

    @patch("fabric_jumpstart.workspace_manager.resolve_token_credential")
    @patch("fabric_jumpstart.workspace_manager.FabricWorkspace")
    def test_credential_passed_to_fabric_workspace(self, mock_fw, mock_resolve):
        """Resolved credential is forwarded to FabricWorkspace."""
        from fabric_jumpstart.workspace_manager import WorkspaceManager
        from pathlib import Path

        fake_cred = MagicMock()
        mock_resolve.return_value = fake_cred

        wm = WorkspaceManager("ws-id", Path("/tmp"), ["Notebook"])
        wm.get_fabric_workspace()

        mock_fw.assert_called_once()
        call_kwargs = mock_fw.call_args[1]
        assert call_kwargs["token_credential"] is fake_cred
