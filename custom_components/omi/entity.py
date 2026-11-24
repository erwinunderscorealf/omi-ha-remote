"""Gemeenschappelijke basis voor Omi-entiteiten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .hanger import OmiHanger


class OmiEntiteit(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hanger: OmiHanger, sleutel: str) -> None:
        self._hanger = hanger
        self._attr_translation_key = sleutel
        self._attr_unique_id = f"{hanger.address}_{sleutel}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, hanger.address)},
            name=hanger.naam,
            manufacturer="Based Hardware",
            model="Omi",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._hanger.async_add_listener(self.async_write_ha_state))
