import pkgutil
import sys

from pathlib import Path

import pytest


class ModuleInfo:
    def __init__(self, name):
        self.name = name


def _fake_iter_modules_nopers(path=None):
    return [ModuleInfo(name="nopers")]


def _fake_iter_modules_stdlib(path=None):
    return [ModuleInfo(name="sys"), ModuleInfo(name="pkgutil")]


@pytest.fixture
def reset_vendor():
    import goose_proxy

    vendor_path = str(Path(goose_proxy.__file__).parent / "_vendor")
    saved_path = list(sys.path)

    [sys.path.remove(path) for path in sys.path if path == vendor_path]
    removed_modules = [sys.modules.pop(package, None) for package in ["goose_proxy._vendor", "goose_proxy"]]

    yield

    sys.path[:] = saved_path
    for module in removed_modules:
        if module:
            sys.modules[module.__name__] = module


def test_package_masking():
    from goose_proxy import _vendor

    assert getattr(_vendor, "__path__") == []


def test_vendored(reset_vendor, monkeypatch):
    monkeypatch.setattr(pkgutil, "iter_modules", _fake_iter_modules_nopers)

    previous_path = list(sys.path)
    import goose_proxy

    vendor_path = str(Path(goose_proxy.__file__).parent / "_vendor")
    new_path = list(sys.path)

    assert new_path[0] == vendor_path
    assert new_path[1:] == previous_path


def test_vendored_warning(reset_vendor, monkeypatch):
    monkeypatch.setattr(pkgutil, "iter_modules", _fake_iter_modules_stdlib)

    previous_path = list(sys.path)
    import goose_proxy

    vendor_path = str(Path(goose_proxy.__file__).parent / "_vendor")
    new_path = list(sys.path)

    with pytest.warns(UserWarning) as warn:
        goose_proxy._vendor._vendor_paths()  # pyright: ignore[reportAttributeAccessIssue]

    assert new_path[0] == vendor_path
    assert new_path[1:] == previous_path
    assert any(["pkgutil, sys" in str(w.message) for w in warn])
