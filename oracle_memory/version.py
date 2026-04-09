"""Version check — notify users when a newer oracle-protocol release is available on PyPI."""
from __future__ import annotations

import json
import warnings
from urllib.request import urlopen, Request
from urllib.error import URLError

__all__ = ["check_for_updates", "CURRENT_VERSION"]

CURRENT_VERSION = "1.0.0"
_PYPI_URL = "https://pypi.org/pypi/oracle-mempalace/json"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse '0.2.0' into (0, 2, 0) for comparison."""
    return tuple(int(x) for x in v.strip().split(".") if x.isdigit())


def check_for_updates(timeout: float = 3.0, warn: bool = True) -> dict[str, str]:
    """Check PyPI for a newer version of oracle-protocol.

    Returns a dict with 'current', 'latest', and 'update_available' keys.
    Never raises — returns gracefully on network errors.

    Usage:
        from oracle_memory.version import check_for_updates
        info = check_for_updates()
        if info['update_available']:
            print(f"New version {info['latest']} available!  pip install --upgrade oracle-mempalace")
    """
    result = {
        "current": CURRENT_VERSION,
        "latest": CURRENT_VERSION,
        "update_available": False,
        "update_command": "",
    }
    try:
        req = Request(_PYPI_URL, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = data.get("info", {}).get("version", CURRENT_VERSION)
        result["latest"] = latest
        if _parse_version(latest) > _parse_version(CURRENT_VERSION):
            result["update_available"] = True
            result["update_command"] = "pip install --upgrade oracle-mempalace"
            if warn:
                warnings.warn(
                    f"oracle-protocol {latest} is available (you have {CURRENT_VERSION}). "
                    f"Run: pip install --upgrade oracle-mempalace",
                    stacklevel=2,
                )
    except (URLError, OSError, ValueError, KeyError):
        pass  # Network errors are expected — don't break the user's code
    return result
