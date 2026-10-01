"""Shared fixtures: load the plugin package and isolate HERMES_HOME.

The repo root *is* the plugin package (``plugin.yaml`` + ``__init__.py``),
the same layout Hermes clones into ``~/.hermes/plugins/<name>/``. Hermes
imports it as a package so its relative ``from ._shared import`` works;
this conftest does the same under the name ``dashboard_auth_ldap``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "dashboard_auth_ldap"


def _load_plugin_package() -> None:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)


_load_plugin_package()


@pytest.fixture(autouse=True)
def _isolate_hermes_home(tmp_path, monkeypatch):
    """Never read or write the developer's real ~/.hermes."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
