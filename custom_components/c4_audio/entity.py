"""Shared entity helpers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import C4AudioCoordinator
from .entity_ids import entity_unique_id


@callback
def adopt_zone_area(
    hass: HomeAssistant, coordinator: C4AudioCoordinator, entity_id: str, zone: int
) -> None:
    """Put an entity in its zone's room. An area the user already set is kept."""
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.area_id is not None:
        return
    player_id = registry.async_get_entity_id(
        "media_player", DOMAIN, entity_unique_id(coordinator.entry, f"zone_{zone}")
    )
    player = registry.async_get(player_id) if player_id else None
    area_id = (player.area_id if player else None) or coordinator.zone_area_id(zone)
    if area_id:
        registry.async_update_entity(entity_id, area_id=area_id)
