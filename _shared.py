"""Config resolution and register() bookkeeping for the LDAP provider.

Adapted from hermes-agent's ``plugins/dashboard_auth/_shared.py`` (MIT,
Nous Research). That module is internal to the Hermes tree, so an
out-of-tree plugin carries its own copy of the few helpers it needs rather
than importing a private path that can move without notice.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from hermes_cli.dashboard_auth import LoginStart, ProviderError, Session


# ---- Config / env resolution ----

def load_config_section(logger: logging.Logger, tag: str, *path: str) -> dict:
    """The ``config.yaml`` block at ``path`` as a dict, or ``{}`` — robust to load_config()
    raising (fresh install, malformed YAML), absent keys, or a non-dict value."""
    try:
        from hermes_cli.config import cfg_get, load_config

        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — broad catch is intentional
        logger.debug("%s: load_config() raised %s; falling back to env-only configuration", tag, exc)
        return {}
    section = cfg_get(cfg, *path, default=None)
    return section if isinstance(section, dict) else {}


def resolve_env_or_cfg(env_name: str, cfg_value: Any) -> str:
    """Env-wins-over-config; an empty env value is treated as unset so a
    provisioned-but-blank secret can't shadow a valid config.yaml entry."""
    return os.environ.get(env_name, "").strip() or str(cfg_value or "").strip()


# ---- register() bookkeeping ----

class SkipRegistration(Exception):
    """Raised by the settings resolver to decline registration; ``reason`` is
    the operator-facing text stored in the module's ``LAST_SKIP_REASON``."""

    def __init__(self, reason: str, level: str = "debug") -> None:
        super().__init__(reason)
        self.reason, self.level = reason, level


def register_provider(
    ctx, logger: logging.Logger, tag: str, provider_cls: type, settings: Callable[[], dict],
) -> tuple[Optional[dict], str]:
    """Build ``provider_cls(**settings())`` and register it on ``ctx``.

    Returns ``(kwargs, "")`` on success, ``(None, skip_reason)`` when ``settings`` raised
    ``SkipRegistration`` (logged at its level) or construction raised ``ValueError`` /
    ``ProviderError`` (logged as a warning).
    """
    try:
        kwargs = settings()
        provider = provider_cls(**kwargs)
    except SkipRegistration as skip:
        getattr(logger, skip.level)("%s: %s", tag, skip.reason)
        return None, skip.reason
    except (ValueError, ProviderError) as exc:
        reason = f"{provider_cls.__name__} construction failed: {exc}"
        logger.warning("%s: %s", tag, reason)
        return None, reason
    ctx.register_dashboard_auth_provider(provider)
    return kwargs, ""


# ---- Provider skeleton ----

class NonInteractiveMixin:
    """OAuth-redirect stubs for a provider without a browser login flow.
    ``_NOT_INTERACTIVE`` is the operator-facing reason; ``_NO_START_LOGIN``
    optionally overrides the ``start_login`` message."""

    _NOT_INTERACTIVE: str = ""
    _NO_START_LOGIN: str = ""

    def start_login(self, *, redirect_uri: str) -> LoginStart:
        raise NotImplementedError(self._NO_START_LOGIN or self._NOT_INTERACTIVE)

    def complete_login(self, *, code: str, state: str, code_verifier: str, redirect_uri: str) -> Session:
        raise NotImplementedError(self._NOT_INTERACTIVE)
