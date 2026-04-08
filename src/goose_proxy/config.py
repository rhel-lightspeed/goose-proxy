"""Schemas for the backend config."""

import logging
import os
import sys

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


#: Define the config file path.
CONFIG_FILE_DEFINITION: tuple[str, str] = (
    "goose-proxy",
    "config.toml",
)

logger = logging.getLogger(__name__)


def get_xdg_config_path() -> Path:
    """Check for the existence of XDG_CONFIG_DIRS environment variable.

    In case it is not present, this function will return the default path that
    is `/etc/xdg`, which is where we want to locate our configuration file for
    goose-proxy.

    $XDG_CONFIG_DIRS defines the preference-ordered set of base directories to
    search for configuration files in addition to the $XDG_CONFIG_HOME base
    directory. The first entry in the variable that exists will be returned.

        .. note::
            Usually, XDG_CONFIG_DIRS is represented as multi-path separated by a
            ":" where all the configurations files could live. This is not
            particularly useful to us, so we read the environment (if present),
            parse that, and extract only the wanted path (/etc/xdg).

    Ref: https://specifications.freedesktop.org/basedir-spec/latest/
    """
    xdg_config_dirs_env: str = os.getenv("XDG_CONFIG_DIRS", "")
    xdg_config_dirs: list[str] = xdg_config_dirs_env.split(os.pathsep) if xdg_config_dirs_env else []
    wanted_xdg_path = Path("/etc/xdg")

    # In case XDG_CONFIG_DIRS is not set yet, we return the path we want.
    if not xdg_config_dirs:
        return wanted_xdg_path

    # If the total length of XDG_CONFIG_DIRS is just 1, we don't need to
    # proceed on the rest of the conditions. This probably means that the
    # XDG_CONFIG_DIRS was overridden and pointed to a specific location.
    # We hope to find the config file there.
    if len(xdg_config_dirs) == 1:
        return Path(xdg_config_dirs[0])

    # Try to find the first occurrence of a directory in the path that exists
    # and return it. If no path exists, return the default value.
    xdg_dir_found = next((dir for dir in xdg_config_dirs if os.path.exists(dir)), wanted_xdg_path)
    return Path(xdg_dir_found)


class Logging(BaseModel):
    """This class represents the [logging] section of our config.toml file.

    Attributes:
        level (str): The level to log. Defaults to "INFO".
    """

    level: str = "INFO"

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        """Post initialization method to normalize values

        Raises:
            ValueError: In case the requested level i snot in the allowed_levels list.
        """
        level = v.upper()
        allowed_levels = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET")
        if level not in allowed_levels:
            raise ValueError(f"The requested level '{level}' is not allowed. Choose from: {', '.join(allowed_levels)}")

        return level


def _resolve_credential(name: str, fallback: str) -> Path:
    """Resolve a credential path from systemd's CREDENTIALS_DIRECTORY.

    When running under systemd with LoadCredential=, credentials are placed in
    a secure directory referenced by $CREDENTIALS_DIRECTORY. This function
    checks there first and falls back to the traditional filesystem path.
    """
    creds_dir = os.getenv("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_path = Path(creds_dir) / name
        if cred_path.exists():
            return cred_path

    return Path(fallback)


class Auth(BaseModel):
    """Internal schema that represents the authentication for goose-proxy.

    Attributes:
        cert_file (Path): The path to the RHSM certificate file
        key_file (Path): The path to the RHSM key file
    """

    cert_file: Path = Field(default_factory=lambda: _resolve_credential("cert.pem", "/etc/pki/consumer/cert.pem"))
    key_file: Path = Field(default_factory=lambda: _resolve_credential("key.pem", "/etc/pki/consumer/key.pem"))


class Backend(BaseModel):
    """This class represents the [backend] section of our config.toml file.

    Attributes:
        endpoint (str): The endpoint to communicate with.
        proxy (str): The proxy URL to route requests through
        auth (Auth): The authentication information
        timeout (int): HTTP request timeout in seconds
    """

    endpoint: str = "https://0.0.0.0:8080"
    auth: Auth = Field(default_factory=Auth)
    proxy: str = ""
    timeout: int = 30


class Server(BaseModel):
    """These are the settings that control how gunicorn runs the application."""

    host: str = "127.0.0.1"
    port: int = 8080
    reload: bool = False
    workers: int = 1


class Settings(BaseModel):
    backend: Backend = Field(default_factory=Backend)
    logging: Logging = Field(default_factory=Logging)
    server: Server = Field(default_factory=Server)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    This avoids re-parsing the TOML config file every time settings are needed
    and makes the configuration available before the ASGI lifespan runs.
    """
    config_path = Path(get_xdg_config_path(), *CONFIG_FILE_DEFINITION)

    data = {}
    try:
        raw = config_path.read_text()
        data = tomllib.loads(raw)
    except FileNotFoundError:
        logger.warning("Config file not found at %s, using defaults.", config_path)

    return Settings(**data)
