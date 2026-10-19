"""Tests for goose-init.sh migration logic."""
import shutil
import subprocess

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
GOOSE_INIT = REPO_ROOT / "data" / "release" / "goose" / "goose-init.sh"
RELEASE_DIR = REPO_ROOT / "data" / "release" / "goose"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def goose_redhat_dir(tmp_path):
    redhat_dir = tmp_path / "goose-redhat"
    redhat_dir.mkdir()
    shutil.copy(RELEASE_DIR / "config.yaml", redhat_dir / "config.yaml")
    shutil.copy(RELEASE_DIR / "rhel_cla.json", redhat_dir / "rhel_cla.json")
    return redhat_dir


def run_init(home, redhat_dir, *args, extra_env=None):
    env = {"HOME": str(home), "GOOSE_REDHAT_DIR": str(redhat_dir)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(GOOSE_INIT), *args],
        env=env,
        capture_output=True,
        text=True,
    )

@pytest.fixture()
def config_file(tmp_path):
    return tmp_path / "home" / ".config" / "goose" / "config.yaml"


@pytest.fixture()
def provider_file(tmp_path):
    return tmp_path / "home" / ".config" / "goose" / "custom_providers" / "rhel_cla.json"



class TestFreshInstall:
    def test_config_created_with_correct_base_path(self, tmp_path, config_file, goose_redhat_dir):
        home = tmp_path / "home"
        run_init(home, goose_redhat_dir)
        assert "OPENAI_BASE_PATH: v1/responses" in config_file.read_text()

    def test_custom_provider_created(self, tmp_path, provider_file, goose_redhat_dir):
        home = tmp_path / "home"
        run_init(home, goose_redhat_dir)
        assert provider_file.exists()


class TestExistingConfigNoFlag:
    def test_stale_base_path_not_updated(self, tmp_path, config_file, goose_redhat_dir):
        home = tmp_path / "home"
        config_file.parent.mkdir(parents=True)
        config_file.write_text((FIXTURES_DIR / "goose_real_config.yml").read_text())

        run_init(home, goose_redhat_dir)

        assert "OPENAI_BASE_PATH: v1/chat/completions" in config_file.read_text()

    def test_custom_setting_preserved(self, tmp_path, config_file, goose_redhat_dir):
        home = tmp_path / "home"
        config_file.parent.mkdir(parents=True)
        config_file.write_text((FIXTURES_DIR / "goose_real_config.yml").read_text())

        run_init(home, goose_redhat_dir)

        assert "MY_CUSTOM_SETTING: keep_this" in config_file.read_text()


@pytest.mark.parametrize(
    "migrate_args,migrate_env",
    [
        (("--migrate",), None),
        ((), {"GOOSE_MIGRATE": "1"}),
    ],
    ids=["flag", "env_var"],
)
class TestMigrate:
    def test_stale_base_path_updated(
        self, tmp_path, config_file, goose_redhat_dir, migrate_args, migrate_env
    ):
        home = tmp_path / "home"
        config_file.parent.mkdir(parents=True)
        config_file.write_text((FIXTURES_DIR / "goose_real_config.yml").read_text())

        run_init(home, goose_redhat_dir, *migrate_args, extra_env=migrate_env)

        assert "OPENAI_BASE_PATH: v1/responses" in config_file.read_text()

    def test_custom_setting_preserved(
        self, tmp_path, config_file, goose_redhat_dir, migrate_args, migrate_env
    ):
        home = tmp_path / "home"
        config_file.parent.mkdir(parents=True)
        config_file.write_text((FIXTURES_DIR / "goose_real_config.yml").read_text())

        run_init(home, goose_redhat_dir, *migrate_args, extra_env=migrate_env)

        assert "MY_CUSTOM_SETTING: keep_this" in config_file.read_text()

    def test_missing_key_appended(
        self, tmp_path, config_file, goose_redhat_dir, migrate_args, migrate_env
    ):
        home = tmp_path / "home"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("GOOSE_PROVIDER: rhel_cla\nOPENAI_HOST: http://127.0.0.1:7080\n")

        run_init(home, goose_redhat_dir, *migrate_args, extra_env=migrate_env)

        assert "OPENAI_BASE_PATH: v1/responses" in config_file.read_text()
