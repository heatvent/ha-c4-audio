"""Source picker on the amp/switch device (dropdown on the device page)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .const import DOMAIN, SKIP_NAME
from .coordinator import C4AudioCoordinator

SOURCE_OFF = "Off"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        C4SourceSelect(coordinator, zone) for zone in coordinator.enabled_zones
    )


class C4SourceSelect(CoordinatorEntity[C4AudioCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "source"
    _attr_icon = "mdi:import"

    def __init__(self, coordinator: C4AudioCoordinator, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        kind = "output" if coordinator.is_matrix else "zone"
        self._attr_unique_id = f"{coordinator.host}_{kind}_{zone}_source"
        self._attr_device_info = device_info_for(coordinator)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        switch = self.coordinator.linked_switch()
        if switch is not None:
            self.async_on_remove(switch.async_add_listener(self._handle_switch_update))

    @callback
    def _handle_switch_update(self) -> None:
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        jack = self.coordinator.zone_names[self._zone - 1]
        label = "input" if self.coordinator.is_matrix else "source"
        return f"{jack} {label}"

    @property
    def options(self) -> list[str]:
        return [SOURCE_OFF, *self.coordinator.media_source_list()]

    @property
    def current_option(self) -> str | None:
        name = self.coordinator.media_source_name(self._zone)
        if not name or name == SKIP_NAME:
            return SOURCE_OFF
        if name in self.options:
            return name
        return SOURCE_OFF

    async def async_select_option(self, option: str) -> None:
        if option == SOURCE_OFF:
            await self.coordinator.async_turn_off(self._zone)
            return
        await self.coordinator.async_select_source(self._zone, option)
