"""Verbonden-sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OmiConfigEntry
from .entity import OmiEntiteit


async def async_setup_entry(
    hass: HomeAssistant, entry: OmiConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([OmiVerbonden(entry.runtime_data, "connected")])


class OmiVerbonden(OmiEntiteit, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        return self._hanger.verbonden

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_error": self._hanger.laatste_fout}
