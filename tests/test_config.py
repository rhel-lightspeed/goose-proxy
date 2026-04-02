"""Tests for configuration loading and validation."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from goose_proxy.config import Logging, Auth, Backend, Server, get_xdg_config_path


class TestLogging:
    def test_default_level(self):
        log = Logging()
        assert log.level == "INFO"

    @pytest.mark.parametrize("level", ["debug", "DEBUG", "Debug"])
    def test_level_normalized_to_uppercase(self, level):
        log = Logging(level=level)
        assert log.level == "DEBUG"

    @pytest.mark.parametrize(
        "level", ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]
    )
    def test_all_valid_levels(self, level):
        log = Logging(level=level)
        assert log.level == level

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            Logging(level="TRACE")


class TestAuth:
    def test_default_cert_paths(self):
        auth = Auth()
        assert auth.cert_file == Path("/etc/pki/consumer/cert.pem")
        assert auth.key_file == Path("/etc/pki/consumer/key.pem")

    def test_custom_cert_paths(self):
        auth = Auth(cert_file="/tmp/cert.pem", key_file="/tmp/key.pem")
        assert auth.cert_file == Path("/tmp/cert.pem")
        assert auth.key_file == Path("/tmp/key.pem")


class TestBackend:
    def test_defaults(self):
        b = Backend()
        assert b.endpoint == "https://0.0.0.0:8080"
        assert b.proxy == ""
        assert b.timeout == 30
        assert isinstance(b.auth, Auth)

    def test_custom_values(self):
        b = Backend(
            endpoint="https://example.com", proxy="http://proxy:8080", timeout=60
        )
        assert b.endpoint == "https://example.com"
        assert b.proxy == "http://proxy:8080"
        assert b.timeout == 60


class TestServer:
    def test_defaults(self):
        s = Server()
        assert s.host == "127.0.0.1"
        assert s.port == 8080
        assert s.reload is False
        assert s.workers == 1

    def test_custom_values(self):
        s = Server(host="0.0.0.0", port=9090, reload=True, workers=4)
        assert s.host == "0.0.0.0"
        assert s.port == 9090
        assert s.reload is True
        assert s.workers == 4


class TestGetXdgConfigPath:
    def test_returns_etc_xdg_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove XDG_CONFIG_DIRS if present
            os.environ.pop("XDG_CONFIG_DIRS", None)
            result = get_xdg_config_path()
        assert result == Path("/etc/xdg")

    def test_returns_single_path_directly(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": str(tmp_path)}):
            result = get_xdg_config_path()
        assert result == tmp_path

    def test_returns_first_existing_path_from_multiple(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        nonexistent = tmp_path / "nonexistent"
        paths = f"{nonexistent}{os.pathsep}{existing}"
        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": paths}):
            result = get_xdg_config_path()
        assert result == existing

    def test_returns_etc_xdg_when_no_paths_exist(self, tmp_path):
        paths = f"{tmp_path}/a{os.pathsep}{tmp_path}/b"
        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": paths}):
            result = get_xdg_config_path()
        assert result == Path("/etc/xdg")

    def test_empty_env_var_returns_default(self):
        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": ""}):
            result = get_xdg_config_path()
        assert result == Path("/etc/xdg")
