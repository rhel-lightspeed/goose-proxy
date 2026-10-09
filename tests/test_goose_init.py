"""Tests for goose-init.sh migration logic."""
import shutil
import subprocess

from pathlib import Path
from typing import Any
from typing import Optional

import pytest


REPO_ROOT = Path(__file__).parent.parent
GOOSE_INIT = REPO_ROOT / "data" / "release" / "goose" / "goose-init.sh"
RELEASE_DIR = REPO_ROOT / "data" / "release" / "goose"

STALE_CONFIG = """\
GOOSE_PROVIDER: rhel_cla
OPENAI_BASE_PATH: v1/chat/completions
OPENAI_HOST: http://127.0.0.1:7080
MY_CUSTOM_SETTING: keep_this
"""


@pytest.fixture()
def fake_redhat(tmp_path):
    redhat_dir = tmp_path / "goose-redhat"
    redhat_dir.mkdir()
    shutil.copy(RELEASE_DIR / "config.yaml", redhat_dir / "config.yaml")
    shutil.copy(RELEASE_DIR / "rhel_cla.json", redhat_dir / "rhel_cla.json")
    return redhat_dir


def run_init(home: Path, redhat_dir: Path, *args: str, extra_env: Optional[dict[str, Any]] = None):
    env = {"HOME": str(home), "GOOSE_REDHAT_DIR": str(redhat_dir)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(GOOSE_INIT), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def config_file(home: Path) -> Path:
    return home / ".config" / "goose" / "config.yaml"


def provider_file(home: Path) -> Path:
    return home / ".config" / "goose" / "custom_providers" / "rhel_cla.json"


class TestFreshInstall:
    def test_config_created_with_correct_base_path(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        run_init(home, fake_redhat)
        assert "OPENAI_BASE_PATH: v1/responses" in config_file(home).read_text()

    def test_custom_provider_created(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        run_init(home, fake_redhat)
        assert provider_file(home).exists()


class TestExistingConfigNoFlag:
    def test_stale_base_path_not_updated(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat)

        assert "OPENAI_BASE_PATH: v1/chat/completions" in config_file(home).read_text()

    def test_custom_setting_preserved(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat)

        assert "MY_CUSTOM_SETTING: keep_this" in config_file(home).read_text()


class TestMigrateFlag:
    def test_stale_base_path_updated_with_flag(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat, "--migrate")

        assert "OPENAI_BASE_PATH: v1/responses" in config_file(home).read_text()

    def test_custom_setting_preserved_with_flag(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat, "--migrate")

        assert "MY_CUSTOM_SETTING: keep_this" in config_file(home).read_text()

    def test_missing_key_appended(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(
            "GOOSE_PROVIDER: rhel_cla\nOPENAI_HOST: http://127.0.0.1:7080\n"
        )

        run_init(home, fake_redhat, "--migrate")

        assert "OPENAI_BASE_PATH: v1/responses" in config_file(home).read_text()


class TestMigrateEnvVar:
    def test_stale_base_path_updated_with_env(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat, extra_env={"GOOSE_MIGRATE": "1"})

        assert "OPENAI_BASE_PATH: v1/responses" in config_file(home).read_text()

    def test_custom_setting_preserved_with_env(self, tmp_path, fake_redhat):
        home = tmp_path / "home"
        config_file(home).parent.mkdir(parents=True)
        config_file(home).write_text(STALE_CONFIG)

        run_init(home, fake_redhat, extra_env={"GOOSE_MIGRATE": "1"})

        assert "MY_CUSTOM_SETTING: keep_this" in config_file(home).read_text()
