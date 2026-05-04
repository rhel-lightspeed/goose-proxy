"""Tests for CLI entrypoint and socket activation detection."""

import os

from unittest.mock import patch

import pytest

from goose_proxy.cli import _is_socket_activated
from goose_proxy.cli import SD_LISTEN_FDS_START


@pytest.fixture
def mock_uvicorn():
    def mock_run(*args, **kwargs):
        if kwargs.get("reload") or kwargs.get("workers", 1) > 1:
            if not isinstance(args[0], str):
                raise ValueError("You must pass the application as an import string to enable 'reload' or 'workers'.")

    with patch("goose_proxy.cli.uvicorn", autospec=True) as mock_uvicorn:
        mock_uvicorn.run.side_effect = mock_run
        yield mock_uvicorn


class TestIsSocketActivated:
    def test_returns_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("LISTEN_FDS", raising=False)
        monkeypatch.delenv("LISTEN_PID", raising=False)

        assert _is_socket_activated() is False

    def test_returns_false_when_listen_fds_only(self, monkeypatch):
        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.delenv("LISTEN_PID", raising=False)

        assert _is_socket_activated() is False

    def test_returns_false_when_listen_pid_only(self, monkeypatch):
        monkeypatch.delenv("LISTEN_FDS", raising=False)
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))

        assert _is_socket_activated() is False

    def test_returns_false_when_pid_mismatch(self, monkeypatch):
        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.setenv("LISTEN_PID", "999999")

        assert _is_socket_activated() is False

    def test_returns_true_when_valid(self, monkeypatch):
        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))

        assert _is_socket_activated() is True

    def test_returns_false_when_zero_fds(self, monkeypatch):
        monkeypatch.setenv("LISTEN_FDS", "0")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))

        assert _is_socket_activated() is False

    def test_returns_true_with_multiple_fds(self, monkeypatch):
        monkeypatch.setenv("LISTEN_FDS", "3")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))

        assert _is_socket_activated() is True


class TestServe:
    @pytest.fixture(autouse=True)
    def _clear_settings_cache(self):
        from goose_proxy.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_standalone_passes_host_and_port(self, mock_uvicorn, tmp_path, monkeypatch):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("")

        monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path))
        monkeypatch.delenv("LISTEN_FDS", raising=False)
        monkeypatch.delenv("LISTEN_PID", raising=False)

        from goose_proxy.cli import serve

        serve()

        _, kwargs = mock_uvicorn.run.call_args
        assert "host" in kwargs
        assert "port" in kwargs
        assert "fd" not in kwargs

    def test_socket_activated_passes_fd(self, mock_uvicorn, tmp_path, monkeypatch):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("")

        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path))

        from goose_proxy.cli import serve

        serve()

        _, kwargs = mock_uvicorn.run.call_args
        assert kwargs["fd"] == SD_LISTEN_FDS_START
        assert "host" not in kwargs
        assert "port" not in kwargs
        assert "reload" not in kwargs

    def test_socket_activated_warns_on_reload(self, mock_uvicorn, tmp_path, caplog, monkeypatch):
        config = tmp_path / "goose-proxy" / "config.toml"
        config.parent.mkdir()
        config.write_text("[server]\nreload = true\n")

        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path))

        from goose_proxy.cli import serve

        serve()

        assert "reload" in caplog.text.lower()
        assert "ignored" in caplog.text.lower()
