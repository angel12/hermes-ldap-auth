"""End-to-end: Hermes's real PluginManager discovers this repo as a user plugin.

Copies the plugin into ``$HERMES_HOME/plugins/<manifest name>/`` (exactly
where ``hermes plugins install`` clones it) and runs real discovery against
a temp HERMES_HOME. Pins the two contracts that differ from a bundled
provider: a user plugin loads only once enabled, and once enabled and
configured it registers the ``ldap`` provider in the dashboard auth registry.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from hermes_cli.dashboard_auth.registry import clear_providers, get_provider
from hermes_cli.plugins import PluginManager

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_FILES = ("plugin.yaml", "pyproject.toml", "__init__.py", "_shared.py")
MANIFEST_NAME = re.search(r"^name:\s*(\S+)", (REPO_ROOT / "plugin.yaml").read_text(), re.M).group(1)

LDAP_CONFIG = {
    "server_url": "ldaps://ldap.example.com",
    "user_dn_template": "uid={username},ou=people,dc=example,dc=com",
    "secret": "a" * 32,
}


@pytest.fixture
def installed_home(_isolate_hermes_home, monkeypatch):
    for var in ("HERMES_DASHBOARD_LDAP_SERVER_URL", "HERMES_DASHBOARD_LDAP_USER_DN_TEMPLATE"):
        monkeypatch.delenv(var, raising=False)
    plugin_dir = _isolate_hermes_home / "plugins" / MANIFEST_NAME
    plugin_dir.mkdir(parents=True)
    for name in PLUGIN_FILES:
        shutil.copy2(REPO_ROOT / name, plugin_dir / name)
    clear_providers()
    yield _isolate_hermes_home
    clear_providers()


def _write_config(home: Path, *, enabled: list[str]) -> None:
    # JSON is valid YAML; Hermes no longer ships PyYAML.
    (home / "config.yaml").write_text(json.dumps({
        "plugins": {"enabled": enabled},
        "dashboard": {"ldap_auth": LDAP_CONFIG},
    }))


def test_enabled_plugin_registers_ldap_provider(installed_home):
    _write_config(installed_home, enabled=[MANIFEST_NAME])

    PluginManager().discover_and_load(force=True)

    provider = get_provider("ldap")
    assert provider is not None
    assert provider.supports_password is True


def test_installed_but_not_enabled_registers_nothing(installed_home):
    _write_config(installed_home, enabled=[])

    PluginManager().discover_and_load(force=True)

    assert get_provider("ldap") is None
