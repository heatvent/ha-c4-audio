"""Media player entities — one per enabled zone or switch output."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
        C4ZoneMediaPlayer(coordinator, zone) for zone in coordinator.enabled_zones
    )


class C4ZoneMediaPlayer(CoordinatorEntity[C4AudioCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "zone"
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: C4AudioCoordinator, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"{coordinator.host}_zone_{zone}"
        self._attr_device_info = device_info_for(coordinator)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        switch = self.coordinator.linked_switch()
        if switch is not None:
            self.async_on_remove(switch.async_add_listener(self._handle_switch_update))
        registry = er.async_get(self.hass)
        entity_entry = registry.async_get(self.entity_id)
        if self.coordinator.is_matrix:
            if entity_entry is not None and entity_entry.area_id is not None:
                registry.async_update_entity(self.entity_id, area_id=None)
        else:
            area_id = self.coordinator.zone_area_id(self._zone)
            if area_id and (entity_entry is None or entity_entry.area_id != area_id):
                registry.async_update_entity(self.entity_id, area_id=area_id)

    @callback
    def _handle_switch_update(self) -> None:
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        return self.coordinator.zone_names[self._zone - 1]

    @property
    def source_list(self) -> list[str]:
        return self.coordinator.media_source_list()

    @property
    def _zone_state(self):
        return self.coordinator.state.zones[self._zone]

    @property
    def state(self) -> MediaPlayerState:
        zone = self._zone_state
        if zone.source <= 0:
            return MediaPlayerState.OFF
        if zone.muted:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def source(self) -> str | None:
        return self.coordinator.media_source_name(self._zone)

    @property
    def volume_level(self) -> float:
        if self._zone_state.source <= 0:
            return self.coordinator.on_volume / 100.0
        return self._zone_state.volume / 100.0

    @property
    def is_volume_muted(self) -> bool:
        return self._zone_state.muted

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "zone": self._zone,
            "host": self.coordinator.host,
            "model": self.coordinator.model_id,
            "input_index": self._zone_state.source,
            "firmware": self.coordinator.state.firmware,
        }
        switch = self.coordinator.linked_switch()
        if switch is not None:
            feeds = self.coordinator.switch_feeds
            amp_in = self._zone_state.source
            if amp_in in feeds:
                sw_out = feeds[amp_in]
                attrs["switch_output"] = sw_out
                attrs["switch_input"] = switch.state.zones.get(sw_out).source if sw_out in switch.state.zones else None
                attrs["switch_host"] = switch.host
        return attrs

    async def async_turn_on(self) -> None:
        await self.coordinator.async_turn_on(self._zone)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_turn_off(self._zone)

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.async_select_source(self._zone, source)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_set_volume(self._zone, volume)

    async def async_volume_up(self) -> None:
        await self.coordinator.async_adjust_volume(self._zone, 1)

    async def async_volume_down(self) -> None:
        await self.coordinator.async_adjust_volume(self._zone, -1)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_set_mute(self._zone, mute)
