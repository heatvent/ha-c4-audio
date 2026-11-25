"""Stable entity unique IDs that survive a DHCP address change."""

from __future__ import annotations

import re

try:
    from homeassistant.config_entries import ConfigEntry
except ImportError:  # unit tests
    ConfigEntry = object  # type: ignore[misc,assignment]

try:
    from .const import CONF_IDENT
except ImportError:
    from const import CONF_IDENT  # type: ignore

# Suffixes this integration has ever assigned after "{host}_".
_LEGACY_SUFFIX = re.compile(
    r"_(?:zone_\d+(?:_(?:bass|treble|source))?|all_on|all_off|all_zones|udp_activity)$"
)


def stable_instance_id(entry: ConfigEntry) -> str:
    """Chassis identity, or the config entry id when discovery never stored one."""
    ident = entry.data.get(CONF_IDENT)
    if isinstance(ident, str) and ident.strip():
        return ident.strip()
    return entry.entry_id


def entity_unique_id(entry: ConfigEntry, suffix: str) -> str:
    return f"{stable_instance_id(entry)}_{suffix}"


def migrated_unique_id(
    unique_id: str, *, stable_id: str, host: str | None = None
) -> str | None:
    """Map an IP-prefixed unique id onto the stable id. None means leave it."""
    if not unique_id or unique_id.startswith(f"{stable_id}_"):
        return None
    current_host = (host or "").strip()
    if current_host and unique_id.startswith(f"{current_host}_"):
        suffix = unique_id[len(current_host) + 1 :]
        if suffix:
            return f"{stable_id}_{suffix}"
    match = _LEGACY_SUFFIX.search(unique_id)
    if match is None:
        return None
    return f"{stable_id}{match.group(0)}"


_ZONE_SUFFIX = re.compile(r"^zone_(\d+)(_balance)?(?:_|$)")
_INPUT_SUFFIX = re.compile(r"^input_(\d+)_gain$")


def unused_suffix(
    suffix: str, *, zones: list[int], inputs: list[int], balance: bool
) -> bool:
    """True when no entity with this unique-id suffix is created any more."""
    match = _ZONE_SUFFIX.match(suffix)
    if match:
        return int(match.group(1)) not in zones or (bool(match.group(2)) and not balance)
    match = _INPUT_SUFFIX.match(suffix)
    return bool(match) and int(match.group(1)) not in inputs
