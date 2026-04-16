"""Tests for CLI entrypoint and socket activation detection."""

import os

from unittest.mock import patch

import pytest

from goose_proxy.cli import _is_socket_activated
from goose_proxy.cli import SD_LISTEN_FDS_START


class TestIsSocketActivated:
    def test_returns_false_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LISTEN_FDS", None)
            os.environ.pop("LISTEN_PID", None)
            assert _is_socket_activated() is False

    def test_returns_false_when_listen_fds_only(self):
        with patch.dict(os.environ, {"LISTEN_FDS": "1"}, clear=True):
            assert _is_socket_activated() is False

    def test_returns_false_when_listen_pid_only(self):
        with patch.dict(os.environ, {"LISTEN_PID": str(os.getpid())}, clear=True):
            assert _is_socket_activated() is False

    def test_returns_false_when_pid_mismatch(self):
        env = {"LISTEN_FDS": "1", "LISTEN_PID": "999999"}
        with patch.dict(os.environ, env, clear=True):
            assert _is_socket_activated() is False

    def test_returns_true_when_valid(self):
        env = {"LISTEN_FDS": "1", "LISTEN_PID": str(os.getpid())}
        with patch.dict(os.environ, env, clear=True):
            assert _is_socket_activated() is True

    def test_returns_false_when_zero_fds(self):
        env = {"LISTEN_FDS": "0", "LISTEN_PID": str(os.getpid())}
        with patch.dict(os.environ, env, clear=True):
            assert _is_socket_activated() is False

    def test_returns_true_with_multiple_fds(self):
        env = {"LISTEN_FDS": "3", "LISTEN_PID": str(os.getpid())}
        with patch.dict(os.environ, env, clear=True):
            assert _is_socket_activated() is True


class TestServe:
    @pytest.fixture(autouse=True)
    def _clear_settings_cache(self):
        from goose_proxy.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @patch("goose_proxy.cli.uvicorn")
    def test_standalone_passes_host_and_port(self, mock_uvicorn, tmp_path):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("")

        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": str(tmp_path)}, clear=True):
            from goose_proxy.cli import serve

            serve()

        _, kwargs = mock_uvicorn.run.call_args
        assert "host" in kwargs
        assert "port" in kwargs
        assert "fd" not in kwargs

    @patch("goose_proxy.cli.uvicorn")
    def test_socket_activated_passes_fd(self, mock_uvicorn, tmp_path):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("")

        env = {
            "LISTEN_FDS": "1",
            "LISTEN_PID": str(os.getpid()),
            "XDG_CONFIG_DIRS": str(tmp_path),
        }
        with patch.dict(os.environ, env, clear=True):
            from goose_proxy.cli import serve

            serve()

        _, kwargs = mock_uvicorn.run.call_args
        assert kwargs["fd"] == SD_LISTEN_FDS_START
        assert "host" not in kwargs
        assert "port" not in kwargs
        assert "reload" not in kwargs

    @patch("goose_proxy.cli.uvicorn")
    def test_socket_activated_warns_on_reload(self, mock_uvicorn, tmp_path, caplog):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("[server]\nreload = true\n")

        env = {
            "LISTEN_FDS": "1",
            "LISTEN_PID": str(os.getpid()),
            "XDG_CONFIG_DIRS": str(tmp_path),
        }
        with patch.dict(os.environ, env, clear=True):
            from goose_proxy.cli import serve

            serve()

        assert "reload" in caplog.text.lower()
        assert "ignored" in caplog.text.lower()
