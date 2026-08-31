"""Diagnostics for a Control4 audio chassis."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_SWITCH_ENTRY_ID, DOMAIN
from .coordinator import C4AudioCoordinator

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    coordinator: C4AudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "model": coordinator.model_id,
        "firmware": coordinator.state.firmware,
        "available": coordinator.state.available,
        "switch_entry_id": coordinator.entry.options.get(
            CONF_SWITCH_ENTRY_ID, coordinator.entry.data.get(CONF_SWITCH_ENTRY_ID)
        ),
        "switch_feeds": coordinator.switch_feeds,
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
