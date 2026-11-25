"""Diagnostics for a Control4 audio chassis."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_IDENT
from .coordinator import C4AudioCoordinator

# The identity string contains the chassis MAC address.
TO_REDACT = {CONF_HOST, CONF_IDENT, "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    result: dict = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}
    coordinator = getattr(entry, "runtime_data", None)
    if not isinstance(coordinator, C4AudioCoordinator):
        return result
    return {
        **result,
        "model": coordinator.model_id,
        "firmware": coordinator.state.firmware,
        "available": coordinator.state.available,
        "poll_interval": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
        "udp_activity": [
            line.replace(coordinator.host, "**REDACTED**")
            for line in coordinator.client.activity_lines
        ],
        "zones": {
            str(index): {
                "name": coordinator.zone_names[index - 1],
                "source": zone.source,
                "volume": zone.volume,
                "muted": zone.muted,
            }
            for index, zone in coordinator.state.zones.items()
        },
    }
