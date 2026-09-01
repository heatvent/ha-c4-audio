"""All on / All off buttons on each amp or switch device."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .const import DOMAIN
from .coordinator import C4AudioCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            C4AllButton(coordinator, "on"),
            C4AllButton(coordinator, "off"),
        ]
    )


class C4AllButton(CoordinatorEntity[C4AudioCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: C4AudioCoordinator, action: str) -> None:
        super().__init__(coordinator)
        self._action = action
        self._attr_unique_id = f"{coordinator.host}_all_{action}"
        self._attr_device_info = device_info_for(coordinator)
        self._attr_translation_key = "all_on" if action == "on" else "all_off"
        self._attr_icon = "mdi:play-circle" if action == "on" else "mdi:stop-circle-outline"

    async def async_press(self) -> None:
        if self._action == "on":
            await self.coordinator.async_turn_on_all()
        else:
            await self.coordinator.async_turn_off_all()
