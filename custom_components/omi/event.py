"""Knop van de hanger als event-entiteit."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OmiConfigEntry
from .const import KNOP_GEBEURTENIS
from .entity import OmiEntiteit


async def async_setup_entry(
    hass: HomeAssistant, entry: OmiConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([OmiKnop(entry.runtime_data, "button")])


class OmiKnop(OmiEntiteit, EventEntity):
    _attr_event_types = list(KNOP_GEBEURTENIS.values())

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._hanger.async_add_knop_listener(self._druk))

    @callback
    def _druk(self, soort: str) -> None:
        self._trigger_event(soort)
        self.async_write_ha_state()
