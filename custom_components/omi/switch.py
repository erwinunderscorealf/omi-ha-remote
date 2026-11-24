"""Switch 'verbinden': hanger los- of aankoppelen zonder HA te herstarten."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import OmiConfigEntry
from .entity import OmiEntiteit


async def async_setup_entry(
    hass: HomeAssistant, entry: OmiConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([OmiVerbinden(entry.runtime_data, "connect")])


class OmiVerbinden(OmiEntiteit, RestoreEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        vorige = await self.async_get_last_state()
        if vorige is None or vorige.state != STATE_OFF:
            self._hanger.async_start()

    @property
    def is_on(self) -> bool:
        return self._hanger.actief

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._hanger.async_start()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hanger.async_stop()
